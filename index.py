"""
Myanmar HR System — Supabase + Vercel Edition
File  : api/index.py
DB    : Supabase (PostgreSQL)  
Deploy: Vercel
"""

import os, hashlib, secrets
from datetime import date
from functools import wraps
from flask import Flask, request, jsonify, session, make_response
from supabase import create_client

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

def sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def pw(p):
    return hashlib.sha256(p.encode()).hexdigest()

PERMS = {
    "super_admin": dict(view_all=True,manage_emp=True,approve_leave=True,manage_payroll=True,manage_roles=True,view_reports=True),
    "hr_manager":  dict(view_all=True,manage_emp=True,approve_leave=True,manage_payroll=True,manage_roles=False,view_reports=True),
    "employee":    dict(view_all=False,manage_emp=False,approve_leave=False,manage_payroll=False,manage_roles=False,view_reports=False),
}
def current_user(): return session.get("user")
def can(p): u=current_user(); return bool(u and PERMS.get(u.get("role"),{}).get(p,False))
def login_required(f):
    from functools import wraps
    @wraps(f)
    def d(*a,**kw):
        if not current_user(): return jsonify({"ok":False,"msg":"Login မဝင်ရသေးပါ"}),401
        return f(*a,**kw)
    return d

@app.route("/api/login", methods=["POST"])
def api_login():
    d=request.json or {}
    r=sb().table("users").select("*").eq("email",d.get("email","")).eq("password",pw(d.get("password",""))).execute()
    if not r.data: return jsonify({"ok":False,"msg":"Email သို့ Password မှားသည်"})
    session["user"]=r.data[0]
    return jsonify({"ok":True,"user":r.data[0]})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear(); return jsonify({"ok":True})

@app.route("/api/me")
def api_me():
    u=current_user()
    return jsonify({"ok":bool(u),"user":u} if u else {"ok":False})

@app.route("/api/dashboard")
@login_required
def api_dashboard():
    s=sb()
    act=s.table("employees").select("id",count="exact").eq("status","active").execute()
    pnd=s.table("leave_requests").select("id",count="exact").eq("status","pending").execute()
    lv =s.table("leave_requests").select("*").order("created_at",desc=True).limit(5).execute()
    em =s.table("employees").select("*").eq("status","active").order("created_at",desc=True).limit(5).execute()
    an =s.table("announcements").select("*").order("created_at",desc=True).limit(3).execute()
    pm =s.table("payroll").select("month").order("month",desc=True).limit(1).execute()
    total_sal=0
    if pm.data:
        sr=s.table("payroll").select("net_salary").eq("month",pm.data[0]["month"]).execute()
        total_sal=sum(r.get("net_salary",0) for r in sr.data)
    dr=s.table("employees").select("department").eq("status","active").execute()
    depts=len(set(r["department"] for r in dr.data if r.get("department")))
    return jsonify(dict(active=act.count or 0,pending=pnd.count or 0,total_sal=total_sal,depts=depts,
                        recent_leaves=lv.data,recent_emps=em.data,announcements=an.data))

@app.route("/api/employees",methods=["GET"])
@login_required
def api_employees():
    s=sb()
    if can("view_all"): r=s.table("employees").select("*").order("name").execute()
    else: r=s.table("employees").select("*").eq("email",current_user()["email"]).execute()
    return jsonify(r.data)

@app.route("/api/employees",methods=["POST"])
@login_required
def api_add_employee():
    if not can("manage_emp"): return jsonify({"ok":False,"msg":"Permission မရှိပါ"})
    d=request.json or {}
    if not d.get("name") or not d.get("email"): return jsonify({"ok":False,"msg":"Name/Email ဖြည့်ပါ"})
    try:
        r=sb().table("employees").insert({"name":d["name"],"email":d["email"],"phone":d.get("phone",""),
            "department":d.get("department",""),"position":d.get("position",""),
            "salary":float(d.get("salary",0)),"join_date":d.get("join_date",""),
            "status":d.get("status","active")}).execute()
        return jsonify({"ok":True,"id":r.data[0]["id"]})
    except Exception as e: return jsonify({"ok":False,"msg":str(e)})

@app.route("/api/employees/<int:eid>",methods=["PUT"])
@login_required
def api_edit_employee(eid):
    if not can("manage_emp"): return jsonify({"ok":False})
    d=request.json or {}
    try:
        sb().table("employees").update({"name":d.get("name"),"email":d.get("email"),
            "phone":d.get("phone",""),"department":d.get("department",""),
            "position":d.get("position",""),"salary":float(d.get("salary",0)),
            "join_date":d.get("join_date",""),"status":d.get("status","active")}).eq("id",eid).execute()
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"ok":False,"msg":str(e)})

@app.route("/api/employees/<int:eid>/toggle",methods=["POST"])
@login_required
def api_toggle_employee(eid):
    if not can("manage_emp"): return jsonify({"ok":False})
    s=sb(); e=s.table("employees").select("status").eq("id",eid).execute()
    if not e.data: return jsonify({"ok":False})
    ns="inactive" if e.data[0]["status"]=="active" else "active"
    s.table("employees").update({"status":ns}).eq("id",eid).execute()
    return jsonify({"ok":True,"status":ns})

@app.route("/api/leaves",methods=["GET"])
@login_required
def api_leaves():
    s=sb()
    if can("approve_leave"): r=s.table("leave_requests").select("*").order("created_at",desc=True).execute()
    else:
        u=current_user(); e=s.table("employees").select("id").eq("email",u["email"]).execute()
        if e.data: r=s.table("leave_requests").select("*").eq("employee_id",e.data[0]["id"]).order("created_at",desc=True).execute()
        else: return jsonify([])
    return jsonify(r.data)

@app.route("/api/leaves",methods=["POST"])
@login_required
def api_add_leave():
    d=request.json or {}
    if not d.get("start_date") or not d.get("end_date") or not d.get("reason"):
        return jsonify({"ok":False,"msg":"အချက်အလက် ဖြည့်ပါ"})
    u=current_user(); s=sb()
    e=s.table("employees").select("id,name").eq("email",u["email"]).execute()
    eid=e.data[0]["id"] if e.data else 1
    ename=e.data[0]["name"] if e.data else u["name"]
    r=s.table("leave_requests").insert({"employee_id":eid,"employee_name":ename,
        "leave_type":d.get("leave_type","annual"),"start_date":d["start_date"],
        "end_date":d["end_date"],"reason":d["reason"],"status":"pending"}).execute()
    return jsonify({"ok":True,"id":r.data[0]["id"]})

@app.route("/api/leaves/<int:lid>/status",methods=["POST"])
@login_required
def api_leave_status(lid):
    if not can("approve_leave"): return jsonify({"ok":False})
    d=request.json or {}
    sb().table("leave_requests").update({"status":d.get("status","pending")}).eq("id",lid).execute()
    return jsonify({"ok":True})

@app.route("/api/payroll",methods=["GET"])
@login_required
def api_payroll():
    s=sb()
    if can("manage_payroll"): r=s.table("payroll").select("*").order("month",desc=True).execute()
    else:
        u=current_user(); e=s.table("employees").select("id").eq("email",u["email"]).execute()
        if e.data: r=s.table("payroll").select("*").eq("employee_id",e.data[0]["id"]).order("month",desc=True).execute()
        else: return jsonify([])
    return jsonify(r.data)

@app.route("/api/payroll",methods=["POST"])
@login_required
def api_add_payroll():
    if not can("manage_payroll"): return jsonify({"ok":False,"msg":"Permission မရှိပါ"})
    d=request.json or {}; s=sb()
    e=s.table("employees").select("id,name").eq("id",d.get("employee_id")).execute()
    if not e.data: return jsonify({"ok":False,"msg":"ဝန်ထမ်း မတွေ့ပါ"})
    basic=float(d.get("basic_salary",0)); bonus=float(d.get("bonus",0)); ded=float(d.get("deduction",0))
    net=basic+bonus-ded
    r=s.table("payroll").insert({"employee_id":e.data[0]["id"],"employee_name":e.data[0]["name"],
        "month":d.get("month",""),"basic_salary":basic,"bonus":bonus,"deduction":ded,
        "net_salary":net,"paid_date":date.today().isoformat()}).execute()
    return jsonify({"ok":True,"id":r.data[0]["id"],"net":net})

@app.route("/api/reports")
@login_required
def api_reports():
    if not can("view_reports"): return jsonify({"ok":False})
    s=sb()
    emps=s.table("employees").select("department,salary").eq("status","active").execute().data
    dm={}
    for e in emps:
        dep=e.get("department") or "Other"
        if dep not in dm: dm[dep]={"department":dep,"cnt":0,"total_sal":0}
        dm[dep]["cnt"]+=1; dm[dep]["total_sal"]+=float(e.get("salary") or 0)
    dept_data=sorted(dm.values(),key=lambda x:-x["cnt"])
    pays=s.table("payroll").select("month,net_salary").order("month",desc=True).execute().data
    pm={}
    for p in pays:
        m=p["month"]
        if m not in pm: pm[m]={"month":m,"total":0,"cnt":0}
        pm[m]["total"]+=float(p.get("net_salary") or 0); pm[m]["cnt"]+=1
    pay_data=list(pm.values())[:6]
    top=s.table("employees").select("name,department,salary").eq("status","active").order("salary",desc=True).limit(5).execute().data
    return jsonify(dict(dept_data=dept_data,leave_data=[],pay_data=pay_data,top_earners=top))

@app.route("/api/users")
@login_required
def api_users():
    if not can("manage_roles"): return jsonify({"ok":False})
    r=sb().table("users").select("id,name,email,role,department").order("name").execute()
    return jsonify(r.data)

@app.route("/api/users/<int:uid>/role",methods=["POST"])
@login_required
def api_change_role(uid):
    if not can("manage_roles"): return jsonify({"ok":False})
    d=request.json or {}
    sb().table("users").update({"role":d.get("role","employee")}).eq("id",uid).execute()
    return jsonify({"ok":True})

@app.route("/api/announcements",methods=["POST"])
@login_required
def api_add_announcement():
    if not can("manage_emp"): return jsonify({"ok":False})
    d=request.json or {}; u=current_user()
    sb().table("announcements").insert({"title":d.get("title",""),"body":d.get("body",""),"created_by":u["name"]}).execute()
    return jsonify({"ok":True})

@app.route("/")
@app.route("/login")
def index():
    return make_response(HTML)

HTML = r"""<!DOCTYPE html>
<html lang="my">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Myanmar HR System</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0b0d13;--surface:#111420;--surface2:#161a28;--border:#1e2438;--border2:#262d48;
  --text:#e2e8f8;--muted:#7880a0;--hint:#3a4060;
  --gold:#f5a623;--gold2:#e8820a;--blue:#60a5fa;--green:#4ade80;--red:#f87171;--purple:#c084fc;
  --sidebar:200px;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden;}
::-webkit-scrollbar{width:5px;} ::-webkit-scrollbar-track{background:var(--surface);} ::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px;}

/* ── LAYOUT ── */
#app{display:flex;min-height:100vh;}
#sidebar{width:var(--sidebar);background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;position:fixed;top:0;left:0;height:100vh;z-index:100;transition:transform .2s;}
#main{margin-left:var(--sidebar);flex:1;display:flex;flex-direction:column;}
#topbar{padding:14px 24px;background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:50;}
#content{padding:20px 24px;flex:1;}

/* ── SIDEBAR ── */
.s-logo{padding:18px 16px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;}
.s-logo-icon{width:30px;height:30px;background:linear-gradient(135deg,var(--gold),var(--gold2));border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0;}
.s-logo-text{font-family:'Playfair Display',serif;font-size:15px;color:var(--text);}
.user-card{margin:10px 8px;padding:10px;background:var(--surface2);border-radius:8px;border:1px solid var(--border);}
.user-name{font-size:12px;font-weight:600;color:var(--text);margin-bottom:4px;}
.user-dept{font-size:10px;color:var(--hint);}
.role-badge{display:inline-block;font-size:9px;font-weight:700;padding:2px 7px;border-radius:20px;letter-spacing:.4px;margin-bottom:3px;}
.badge-super_admin{background:#3d1a1a;color:var(--gold);border:1px solid #7a2e0e;}
.badge-hr_manager{background:#1a2a3d;color:var(--blue);border:1px solid #1e40af;}
.badge-employee{background:#1a3d2a;color:var(--green);border:1px solid #166534;}
nav{padding:10px 6px;flex:1;overflow-y:auto;}
.nav-label{font-size:9px;font-weight:700;color:var(--hint);letter-spacing:.8px;text-transform:uppercase;padding:6px 10px 3px;}
.nav-item{display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:6px;cursor:pointer;color:var(--muted);font-size:12px;font-weight:500;transition:all .12s;margin-bottom:2px;border:none;background:transparent;width:100%;text-align:left;font-family:'DM Sans',sans-serif;}
.nav-item:hover{background:var(--surface2);color:var(--text);}
.nav-item.active{background:linear-gradient(135deg,#1e2a4a,#1a2340);color:var(--gold);border-left:2px solid var(--gold);}
.nav-icon{font-size:14px;width:18px;text-align:center;}
.sidebar-bottom{padding:10px 8px;border-top:1px solid var(--border);}
.logout-btn{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:6px;cursor:pointer;color:var(--muted);font-size:12px;font-weight:500;border:none;background:transparent;width:100%;transition:all .12s;font-family:'DM Sans',sans-serif;}
.logout-btn:hover{background:#2a1a1a;color:var(--red);}

/* ── TOPBAR ── */
.page-title{font-family:'Playfair Display',serif;font-size:18px;color:var(--text);}
.topbar-right{display:flex;align-items:center;gap:10px;}

/* ── STATS ── */
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px;}
.stat-grid-3{grid-template-columns:repeat(3,1fr);}
.stat-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;}
.stat-icon{font-size:20px;margin-bottom:8px;}
.stat-value{font-size:22px;font-weight:700;color:var(--text);margin-bottom:3px;}
.stat-label{font-size:11px;color:var(--muted);}

/* ── TABLE ── */
.table-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:16px;}
.table-header{padding:13px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;}
.table-title{font-size:13px;font-weight:600;color:var(--text);}
table{width:100%;border-collapse:collapse;}
th{padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--border);background:#0c0e18;}
td{padding:10px 12px;font-size:12px;color:var(--muted);border-bottom:1px solid #0f1118;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:var(--surface2);}
.td-name{font-weight:600;color:var(--text);font-size:12px;}
.td-sub{font-size:10px;color:var(--hint);}

/* ── BADGES ── */
.badge{font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px;display:inline-block;}
.b-active{background:#162a1f;color:var(--green);border:1px solid #166534;}
.b-inactive{background:#2a1a1a;color:var(--red);border:1px solid #7f1d1d;}
.b-pending{background:#2a2215;color:#fbbf24;border:1px solid #92400e;}
.b-approved{background:#162a1f;color:var(--green);border:1px solid #166534;}
.b-rejected{background:#2a1a1a;color:var(--red);border:1px solid #7f1d1d;}
.b-annual{background:#1a2235;color:var(--blue);border:1px solid #1e3a5f;}
.b-sick{background:#2a1a2a;color:var(--purple);border:1px solid #6b21a8;}
.b-emergency{background:#2a1a1a;color:#fb923c;border:1px solid #9a3412;}
.money{color:var(--gold);font-weight:700;}

/* ── BUTTONS ── */
.btn{padding:7px 14px;border-radius:7px;font-size:12px;font-weight:600;cursor:pointer;border:none;transition:all .13s;display:inline-flex;align-items:center;gap:5px;font-family:'DM Sans',sans-serif;}
.btn-primary{background:linear-gradient(135deg,var(--gold),var(--gold2));color:#1a0f00;}
.btn-primary:hover{filter:brightness(1.1);transform:translateY(-1px);}
.btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--border2);}
.btn-ghost:hover{background:var(--surface2);color:var(--text);}
.btn-danger{background:#2a1a1a;color:var(--red);border:1px solid #7f1d1d;}
.btn-danger:hover{background:#3a2020;}
.btn-success{background:#162a1f;color:var(--green);border:1px solid #166534;}
.btn-success:hover{background:#1e3a2a;}
.btn-sm{padding:4px 10px;font-size:11px;}
.btn-row{display:flex;gap:5px;}

/* ── MODAL ── */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:500;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px);}
.modal{background:var(--surface);border:1px solid var(--border2);border-radius:14px;padding:24px;width:480px;max-width:92vw;max-height:88vh;overflow-y:auto;}
.modal-title{font-family:'Playfair Display',serif;font-size:17px;color:var(--text);margin-bottom:18px;}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
.form-group{display:flex;flex-direction:column;gap:5px;}
.form-full{grid-column:1/-1;}
label{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;}
input,select,textarea{background:#0c0e18;border:1px solid var(--border2);color:var(--text);padding:8px 11px;border-radius:7px;font-size:12px;font-family:'DM Sans',sans-serif;width:100%;transition:border-color .13s;}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--gold);}
select option{background:#1a1d27;}
textarea{resize:vertical;min-height:70px;}
.modal-footer{display:flex;gap:8px;justify-content:flex-end;margin-top:18px;}
.net-preview{background:#0c0e18;border:1px solid var(--border);border-radius:7px;padding:10px 12px;display:flex;justify-content:space-between;font-size:13px;}

/* ── TABS ── */
.tab-bar{display:flex;gap:3px;background:#0c0e18;padding:3px;border-radius:8px;border:1px solid var(--border);width:fit-content;margin-bottom:14px;}
.tab{padding:5px 14px;border-radius:6px;cursor:pointer;font-size:11px;font-weight:600;color:var(--hint);border:none;background:transparent;transition:all .12s;font-family:'DM Sans',sans-serif;}
.tab.active{background:var(--surface2);color:var(--gold);}

/* ── SEARCH ── */
.search-input{background:#0c0e18;border:1px solid var(--border2);color:var(--text);padding:7px 12px;border-radius:7px;font-size:12px;font-family:'DM Sans',sans-serif;width:190px;}
.search-input:focus{outline:none;border-color:var(--gold);}

/* ── LOGIN PAGE ── */
.login-page{min-height:100vh;display:flex;align-items:center;justify-content:center;background:radial-gradient(ellipse at 20% 50%,rgba(245,166,35,.05) 0%,transparent 60%),radial-gradient(ellipse at 80% 50%,rgba(96,165,250,.04) 0%,transparent 60%),var(--bg);}
.login-card{background:var(--surface);border:1px solid var(--border2);border-radius:18px;padding:38px;width:400px;max-width:94vw;}
.login-logo{text-align:center;margin-bottom:24px;}
.login-logo-icon{width:52px;height:52px;background:linear-gradient(135deg,var(--gold),var(--gold2));border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:24px;margin:0 auto 10px;}
.login-logo-text{font-family:'Playfair Display',serif;font-size:22px;color:var(--text);}
.login-sub{font-size:12px;color:var(--muted);text-align:center;margin-bottom:22px;}
.demo-hint{background:var(--surface2);border:1px solid var(--border);border-radius:9px;padding:13px;margin-bottom:18px;}
.demo-hint-title{font-size:10px;font-weight:700;color:var(--gold);text-transform:uppercase;letter-spacing:.5px;margin-bottom:9px;}
.demo-row{display:flex;justify-content:space-between;font-size:11px;margin-bottom:5px;color:var(--muted);}
.demo-role{font-weight:700;color:var(--text);}
.error-msg{background:#2a1515;border:1px solid #7f1d1d;color:var(--red);padding:9px 13px;border-radius:7px;font-size:12px;margin-bottom:14px;display:none;}
.form-g1{margin-bottom:12px;}

/* ── REPORTS ── */
.bar-track{background:#0c0e18;border-radius:4px;height:7px;overflow:hidden;margin-top:6px;}
.bar-fill{height:100%;border-radius:4px;background:linear-gradient(90deg,var(--gold),var(--gold2));transition:width .8s ease;}
.report-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;}

/* ── ANNOUNCEMENT ── */
.ann-card{background:var(--surface2);border:1px solid var(--border);border-radius:9px;padding:14px;margin-bottom:10px;}
.ann-title{font-size:13px;font-weight:600;color:var(--text);margin-bottom:5px;}
.ann-body{font-size:12px;color:var(--muted);margin-bottom:6px;}
.ann-meta{font-size:10px;color:var(--hint);}

/* ── MISC ── */
.empty{text-align:center;padding:36px;color:var(--hint);font-size:13px;}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.hidden{display:none;}
.page{display:none;}
.page.active{display:block;}
.toast{position:fixed;bottom:24px;right:24px;background:var(--surface);border:1px solid var(--border2);color:var(--text);padding:12px 18px;border-radius:9px;font-size:13px;font-weight:500;z-index:9999;box-shadow:0 4px 20px rgba(0,0,0,.5);transform:translateY(100px);opacity:0;transition:all .3s;}
.toast.show{transform:translateY(0);opacity:1;}
.toast.ok{border-color:#166534;color:var(--green);}
.toast.err{border-color:#7f1d1d;color:var(--red);}
.denied{text-align:center;padding:60px 20px;}
.denied-icon{font-size:48px;margin-bottom:12px;}
</style>
</head>
<body>

<!-- ══════════════════════════════════════
     LOGIN PAGE
══════════════════════════════════════ -->
<div id="login-page" class="login-page hidden">
  <div class="login-card">
    <div class="login-logo">
      <div class="login-logo-icon">🏢</div>
      <div class="login-logo-text">HR System</div>
    </div>
    <p class="login-sub">Myanmar Company HR Portal</p>
    <div class="demo-hint">
      <div class="demo-hint-title">🔑 Demo Accounts</div>
      <div class="demo-row"><span class="demo-role">⭐ Super Admin</span><span>admin@hr.com / admin123</span></div>
      <div class="demo-row"><span class="demo-role">🔵 HR Manager</span><span>hr@hr.com / hr123</span></div>
      <div class="demo-row"><span class="demo-role">🟢 Employee</span><span>emp@hr.com / emp123</span></div>
    </div>
    <div id="login-err" class="error-msg"></div>
    <div class="form-g1"><label>Email</label><input id="l-email" type="email" placeholder="your@email.com"></div>
    <div class="form-g1"><label>Password</label><input id="l-pw" type="password" placeholder="••••••••"></div>
    <button class="btn btn-primary" style="width:100%;justify-content:center;padding:11px;margin-top:4px" onclick="doLogin()">ဝင်ရောက်ရန် →</button>
  </div>
</div>

<!-- ══════════════════════════════════════
     MAIN APP
══════════════════════════════════════ -->
<div id="main-app" class="hidden">
<div id="app">

  <!-- SIDEBAR -->
  <aside id="sidebar">
    <div class="s-logo">
      <div class="s-logo-icon">🏢</div>
      <span class="s-logo-text">HR System</span>
    </div>
    <div class="user-card">
      <div id="s-name" class="user-name"></div>
      <div id="s-badge"></div>
      <div id="s-dept" class="user-dept"></div>
    </div>
    <nav id="nav"></nav>
    <div class="sidebar-bottom">
      <button class="logout-btn" onclick="doLogout()"><span>🚪</span>ထွက်ရန်</button>
    </div>
  </aside>

  <!-- MAIN -->
  <div id="main">
    <div id="topbar">
      <span id="page-title" class="page-title">Dashboard</span>
      <div class="topbar-right">
        <span style="font-size:11px;color:var(--hint)">Myanmar HR Portal</span>
        <span id="top-badge"></span>
      </div>
    </div>
    <div id="content">

      <!-- DASHBOARD -->
      <div id="p-dashboard" class="page">
        <div id="dash-stats" class="stat-grid"></div>
        <div class="two-col">
          <div>
            <div class="table-card">
              <div class="table-header"><span class="table-title">🕐 နောက်ဆုံး ခွင့်လျှောက်မှုများ</span></div>
              <table><thead><tr><th>ဝန်ထမ်း</th><th>အမျိုးအစား</th><th>Status</th></tr></thead>
              <tbody id="dash-leaves"></tbody></table>
            </div>
            <div id="dash-announce"></div>
          </div>
          <div class="table-card">
            <div class="table-header"><span class="table-title">👥 ဝန်ထမ်းများ</span></div>
            <table><thead><tr><th>အမည်</th><th>ဌာန</th><th>လစာ</th></tr></thead>
            <tbody id="dash-emps"></tbody></table>
          </div>
        </div>
      </div>

      <!-- EMPLOYEES -->
      <div id="p-employees" class="page">
        <div class="table-card">
          <div class="table-header">
            <span class="table-title">👥 ဝန်ထမ်းစာရင်း</span>
            <div style="display:flex;gap:8px;align-items:center">
              <input class="search-input" id="emp-search" placeholder="🔍 ရှာဖွေ..." oninput="filterEmps()">
              <button id="btn-add-emp" class="btn btn-primary btn-sm hidden" onclick="openModal('emp')">＋ ထည့်ရန်</button>
            </div>
          </div>
          <div style="padding:10px 14px">
            <div class="tab-bar">
              <button class="tab active" onclick="setEmpTab('all',this)">အားလုံး</button>
              <button class="tab" onclick="setEmpTab('active',this)">တက်ကြွ</button>
              <button class="tab" onclick="setEmpTab('inactive',this)">ရပ်ဆိုင်း</button>
            </div>
          </div>
          <table><thead><tr><th>အမည်</th><th>ဌာန</th><th>ရာထူး</th><th>ဖုန်း</th><th>လစာ</th><th>Status</th><th id="emp-action-head"></th></tr></thead>
          <tbody id="emp-body"></tbody></table>
        </div>
      </div>

      <!-- LEAVE -->
      <div id="p-leave" class="page">
        <div class="table-card">
          <div class="table-header">
            <span class="table-title">🏖️ ခွင့်စီမံခန့်ခွဲမှု</span>
            <button class="btn btn-primary btn-sm" onclick="openModal('leave')">＋ ခွင့်လျှောက်ရန်</button>
          </div>
          <div style="padding:10px 14px">
            <div class="tab-bar">
              <button class="tab active" onclick="setLeaveTab('all',this)">အားလုံး</button>
              <button class="tab" onclick="setLeaveTab('pending',this)">စောင့်ဆိုင်းဆဲ</button>
              <button class="tab" onclick="setLeaveTab('approved',this)">ခွင့်ပြု</button>
              <button class="tab" onclick="setLeaveTab('rejected',this)">ပယ်ချ</button>
            </div>
          </div>
          <table><thead><tr><th>ဝန်ထမ်း</th><th>အမျိုးအစား</th><th>ကာလ</th><th>အကြောင်းအရင်း</th><th>Status</th><th id="leave-action-head"></th></tr></thead>
          <tbody id="leave-body"></tbody></table>
        </div>
      </div>

      <!-- PAYROLL -->
      <div id="p-payroll" class="page">
        <div id="pay-stats" class="stat-grid stat-grid-3" style="margin-bottom:16px"></div>
        <div class="table-card">
          <div class="table-header">
            <span class="table-title">💰 လစာစာရင်း</span>
            <div style="display:flex;gap:8px;align-items:center">
              <select id="pay-month-filter" class="search-input" style="width:150px" onchange="renderPayroll()">
                <option value="all">လအားလုံး</option>
              </select>
              <button id="btn-add-pay" class="btn btn-primary btn-sm hidden" onclick="openModal('payroll')">＋ လစာထည့်</button>
            </div>
          </div>
          <table><thead><tr><th>ဝန်ထမ်း</th><th>လ</th><th>မူလလစာ</th><th>ဘောနပ်</th><th>နုတ်ယူမှု</th><th>အသားတင်</th><th>ပေးငွေ့ရက်</th></tr></thead>
          <tbody id="pay-body"></tbody></table>
        </div>
      </div>

      <!-- REPORTS -->
      <div id="p-reports" class="page">
        <div id="reports-content"></div>
      </div>

      <!-- ROLES -->
      <div id="p-roles" class="page">
        <div class="table-card">
          <div class="table-header"><span class="table-title">⚙️ Role စီမံခန့်ခွဲမှု</span></div>
          <table><thead><tr><th>အမည်</th><th>Email</th><th>ဌာန</th><th>လက်ရှိ Role</th><th>ပြောင်းရန်</th></tr></thead>
          <tbody id="roles-body"></tbody></table>
        </div>
      </div>

    </div><!-- content -->
  </div><!-- main -->
</div><!-- app -->
</div><!-- main-app -->

<!-- ══════════════════════════════════════
     MODALS
══════════════════════════════════════ -->
<div id="modal-overlay" class="modal-overlay hidden" onclick="if(event.target===this)closeModal()">

  <!-- Employee Modal -->
  <div id="modal-emp" class="modal hidden">
    <div id="modal-emp-title" class="modal-title">＋ ဝန်ထမ်းအသစ် ထည့်ရန်</div>
    <div class="form-grid">
      <div class="form-group"><label>အမည်</label><input id="e-name" placeholder="Ko/Ma ..."></div>
      <div class="form-group"><label>Email</label><input id="e-email" type="email" placeholder="email@co.com"></div>
      <div class="form-group"><label>ဖုန်းနံပါတ်</label><input id="e-phone" placeholder="09-xxx-xxxxx"></div>
      <div class="form-group"><label>ဌာန</label>
        <select id="e-dept"><option value="">ရွေးချယ်ပါ</option>
          <option>HR</option><option>Engineering</option><option>Finance</option><option>Marketing</option><option>Operations</option>
        </select>
      </div>
      <div class="form-group"><label>ရာထူး</label><input id="e-pos" placeholder="Developer ..."></div>
      <div class="form-group"><label>လစာ (Kyat)</label><input id="e-salary" type="number" placeholder="1000000"></div>
      <div class="form-group"><label>ဝင်ရောက်သည့်ရက်</label><input id="e-join" type="date"></div>
      <div class="form-group"><label>Status</label>
        <select id="e-status"><option value="active">Active</option><option value="inactive">Inactive</option></select>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeModal()">ပယ်ဖျက်</button>
      <button class="btn btn-primary" onclick="saveEmployee()">💾 သိမ်းဆည်းရန်</button>
    </div>
  </div>

  <!-- Leave Modal -->
  <div id="modal-leave" class="modal hidden">
    <div class="modal-title">🏖️ ခွင့်လျှောက်ရန်</div>
    <div class="form-grid">
      <div class="form-group form-full"><label>ခွင့်အမျိုးအစား</label>
        <select id="l-type">
          <option value="annual">Annual Leave (နှစ်ပတ်လည်ခွင့်)</option>
          <option value="sick">Sick Leave (ဖျားနာခွင့်)</option>
          <option value="emergency">Emergency Leave (အရေးပေါ်ခွင့်)</option>
        </select>
      </div>
      <div class="form-group"><label>စတင်ရက်</label><input id="l-start" type="date"></div>
      <div class="form-group"><label>ပြီးဆုံးရက်</label><input id="l-end" type="date"></div>
      <div class="form-group form-full"><label>အကြောင်းအရင်း</label>
        <textarea id="l-reason" placeholder="ခွင့်ယူရသော အကြောင်းအရင်း..."></textarea>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeModal()">ပယ်ဖျက်</button>
      <button class="btn btn-primary" onclick="saveLeave()">📨 လျှောက်ထားရန်</button>
    </div>
  </div>

  <!-- Payroll Modal -->
  <div id="modal-payroll" class="modal hidden">
    <div class="modal-title">💰 လစာသတ်မှတ်ရန်</div>
    <div class="form-grid">
      <div class="form-group form-full"><label>ဝန်ထမ်း</label><select id="p-emp"></select></div>
      <div class="form-group form-full"><label>လ (YYYY-MM)</label><input id="p-month" type="month"></div>
      <div class="form-group"><label>မူလလစာ</label><input id="p-basic" type="number" placeholder="1000000" oninput="updateNet()"></div>
      <div class="form-group"><label>ဘောနပ်</label><input id="p-bonus" type="number" value="0" oninput="updateNet()"></div>
      <div class="form-group form-full"><label>နုတ်ယူမှု</label><input id="p-ded" type="number" value="0" oninput="updateNet()"></div>
      <div class="form-group form-full">
        <div class="net-preview">
          <span style="color:var(--muted)">အသားတင်လစာ</span>
          <span id="net-show" class="money">K 0</span>
        </div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeModal()">ပယ်ဖျက်</button>
      <button class="btn btn-primary" onclick="savePayroll()">💾 သိမ်းဆည်းရန်</button>
    </div>
  </div>

  <!-- Announcement Modal -->
  <div id="modal-announce" class="modal hidden">
    <div class="modal-title">📢 ကြေညာချက် ထည့်ရန်</div>
    <div class="form-grid">
      <div class="form-group form-full"><label>ခေါင်းစဉ်</label><input id="ann-title" placeholder="ကြေညာချက် ခေါင်းစဉ်..."></div>
      <div class="form-group form-full"><label>အကြောင်းအရာ</label><textarea id="ann-body" placeholder="ကြေညာချက် အကြောင်းအရာ..."></textarea></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeModal()">ပယ်ဖျက်</button>
      <button class="btn btn-primary" onclick="saveAnnouncement()">📢 ပြန့်ဝေရန်</button>
    </div>
  </div>

</div><!-- modal-overlay -->

<div id="toast" class="toast"></div>

<!-- ══════════════════════════════════════
     JAVASCRIPT
══════════════════════════════════════ -->
<script>
// ── State ──────────────────────────────
let USER = null;
let EMPS = [], LEAVES = [], PAYROLL = [], EMP_TAB = 'all', LEAVE_TAB = 'all';
let EDIT_EMP_ID = null;

const PERMS = {
  super_admin:{view_all:true,manage_emp:true,approve_leave:true,manage_payroll:true,manage_roles:true,view_reports:true},
  hr_manager: {view_all:true,manage_emp:true,approve_leave:true,manage_payroll:true,manage_roles:false,view_reports:true},
  employee:   {view_all:false,manage_emp:false,approve_leave:false,manage_payroll:false,manage_roles:false,view_reports:false},
};
const can = p => USER && PERMS[USER.role]?.[p];

const ROLE_LABELS = {super_admin:'⭐ Super Admin', hr_manager:'🔵 HR Manager', employee:'🟢 Employee'};
const NAV_ITEMS = [
  {id:'dashboard', icon:'📊', label:'Dashboard',      perm:null},
  {id:'employees', icon:'👥', label:'ဝန်ထမ်းစာရင်း',  perm:'view_all'},
  {id:'leave',     icon:'🏖️', label:'ခွင့်စီမံမှု',     perm:null},
  {id:'payroll',   icon:'💰', label:'လစာစာရင်း',     perm:'manage_payroll'},
  {id:'reports',   icon:'📈', label:'Reports',        perm:'view_reports'},
  {id:'roles',     icon:'⚙️', label:'Role စီမံမှု',    perm:'manage_roles'},
];

// ── Utils ──────────────────────────────
const fmt = n => 'K ' + (parseFloat(n)||0).toLocaleString('en', {maximumFractionDigits:0});
const $  = id => document.getElementById(id);
const api = async (url, method='GET', body=null) => {
  const opts = {method, headers:{'Content-Type':'application/json'}};
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  return r.json();
};

function toast(msg, type='ok') {
  const t = $('toast');
  t.textContent = msg;
  t.className = `toast show ${type}`;
  setTimeout(()=>t.className='toast', 2500);
}

function badge(role) {
  return `<span class="role-badge badge-${role}">${ROLE_LABELS[role]||role}</span>`;
}

function statusBadge(s) {
  return `<span class="badge b-${s}">${s}</span>`;
}

// ── Auth ───────────────────────────────
async function doLogin() {
  const email = $('l-email').value.trim();
  const pw    = $('l-pw').value;
  const r = await api('/api/login','POST',{email, password:pw});
  if (!r.ok) { $('login-err').textContent = r.msg; $('login-err').style.display='block'; return; }
  USER = r.user;
  initApp();
}

async function doLogout() {
  await api('/api/logout','POST');
  USER = null;
  $('main-app').classList.add('hidden');
  $('login-page').classList.remove('hidden');
  $('l-pw').value='';
  $('login-err').style.display='none';
}

async function checkSession() {
  const r = await api('/api/me');
  if (r.ok) { USER = r.user; initApp(); }
  else { $('login-page').classList.remove('hidden'); }
}

// ── App Init ───────────────────────────
function initApp() {
  $('login-page').classList.add('hidden');
  $('main-app').classList.remove('hidden');
  $('s-name').textContent = USER.name;
  $('s-badge').innerHTML  = badge(USER.role);
  $('s-dept').textContent = USER.department;
  $('top-badge').innerHTML = badge(USER.role);

  // Build nav
  const nav = $('nav');
  nav.innerHTML = '<div class="nav-label">Menu</div>';
  NAV_ITEMS.filter(n => !n.perm || can(n.perm)).forEach(n => {
    const btn = document.createElement('button');
    btn.className = 'nav-item';
    btn.id = 'nav-' + n.id;
    btn.innerHTML = `<span class="nav-icon">${n.icon}</span>${n.label}`;
    btn.onclick = () => goto(n.id);
    nav.appendChild(btn);
  });

  // Show/hide action buttons
  if (can('manage_emp')) $('btn-add-emp').classList.remove('hidden');
  if (can('manage_payroll')) $('btn-add-pay').classList.remove('hidden');
  if (can('approve_leave')) { $('leave-action-head').textContent='ဆောင်ရွက်မှု'; }
  if (can('manage_emp')) { $('emp-action-head').textContent='ဆောင်ရွက်မှု'; }

  // Keyboard
  $('l-email').addEventListener('keydown', e => e.key==='Enter' && doLogin());
  $('l-pw').addEventListener('keydown',    e => e.key==='Enter' && doLogin());

  goto('dashboard');
}

// ── Navigation ─────────────────────────
const PAGE_TITLES = {
  dashboard:'📊 Dashboard', employees:'👥 ဝန်ထမ်းစာရင်း',
  leave:'🏖️ ခွင့်စီမံမှု', payroll:'💰 လစာစာရင်း',
  reports:'📈 Reports', roles:'⚙️ Role စီမံမှု'
};

async function goto(page) {
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b=>b.classList.remove('active'));
  const el = $('p-'+page);
  if (el) el.classList.add('active');
  const nb = $('nav-'+page);
  if (nb) nb.classList.add('active');
  $('page-title').textContent = PAGE_TITLES[page]||page;

  if (page==='dashboard')  await loadDashboard();
  if (page==='employees')  await loadEmployees();
  if (page==='leave')      await loadLeaves();
  if (page==='payroll')    await loadPayroll();
  if (page==='reports')    await loadReports();
  if (page==='roles')      await loadRoles();
}

// ── Dashboard ──────────────────────────
async function loadDashboard() {
  const d = await api('/api/dashboard');
  $('dash-stats').innerHTML = `
    <div class="stat-card"><div class="stat-icon">👥</div><div class="stat-value">${d.active}</div><div class="stat-label">တက်ကြွ ဝန်ထမ်းများ</div></div>
    <div class="stat-card"><div class="stat-icon">🏖️</div><div class="stat-value">${d.pending}</div><div class="stat-label">ခွင့် စောင့်ဆိုင်းဆဲ</div></div>
    <div class="stat-card"><div class="stat-icon">💰</div><div class="stat-value" style="font-size:16px">${fmt(d.total_sal)}</div><div class="stat-label">ဤလ လစာစုစုပေါင်း</div></div>
    <div class="stat-card"><div class="stat-icon">🏢</div><div class="stat-value">${d.depts}</div><div class="stat-label">ဌာနများ</div></div>
  `;
  $('dash-leaves').innerHTML = d.recent_leaves.map(l=>`
    <tr><td class="td-name">${l.employee_name}</td>
    <td><span class="badge b-${l.leave_type}">${l.leave_type}</span></td>
    <td>${statusBadge(l.status)}</td></tr>`).join('') || '<tr><td colspan="3" class="empty">မှတ်တမ်းမရှိပါ</td></tr>';
  $('dash-emps').innerHTML = d.recent_emps.map(e=>`
    <tr><td><div class="td-name">${e.name}</div></td>
    <td style="font-size:11px">${e.department}</td>
    <td class="money" style="font-size:11px">${fmt(e.salary)}</td></tr>`).join('');

  let annHtml = '';
  if (can('manage_emp')) annHtml += `<div style="margin-bottom:10px"><button class="btn btn-ghost btn-sm" onclick="openModal('announce')">＋ ကြေညာချက်ထည့်</button></div>`;
  annHtml += d.announcements.map(a=>`
    <div class="ann-card">
      <div class="ann-title">📢 ${a.title}</div>
      <div class="ann-body">${a.body}</div>
      <div class="ann-meta">by ${a.created_by} · ${a.created_at.slice(0,10)}</div>
    </div>`).join('');
  $('dash-announce').innerHTML = annHtml;
}

// ── Employees ──────────────────────────
async function loadEmployees() {
  const data = await api('/api/employees');
  EMPS = data;
  renderEmps();
}

function setEmpTab(tab, el) {
  EMP_TAB = tab;
  document.querySelectorAll('#p-employees .tab').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
  renderEmps();
}

function filterEmps() { renderEmps(); }

function renderEmps() {
  const search = ($('emp-search').value||'').toLowerCase();
  const filtered = EMPS.filter(e => {
    const matchTab = EMP_TAB==='all' || e.status===EMP_TAB;
    const matchSearch = e.name.toLowerCase().includes(search) || (e.department||'').toLowerCase().includes(search);
    return matchTab && matchSearch;
  });
  const showAction = can('manage_emp');
  $('emp-body').innerHTML = filtered.length===0 ?
    `<tr><td colspan="7" class="empty">🔍 ရှာမတွေ့ပါ</td></tr>` :
    filtered.map(e=>`
      <tr>
        <td><div class="td-name">${e.name}</div><div class="td-sub">${e.email}</div></td>
        <td>${e.department||'-'}</td>
        <td>${e.position||'-'}</td>
        <td>${e.phone||'-'}</td>
        <td class="money">${fmt(e.salary)}</td>
        <td>${statusBadge(e.status)}</td>
        ${showAction ? `<td><div class="btn-row">
          <button class="btn btn-ghost btn-sm" onclick="editEmp(${e.id})">✏️</button>
          <button class="btn ${e.status==='active'?'btn-danger':'btn-success'} btn-sm" onclick="toggleEmp(${e.id})">${e.status==='active'?'❌':'✅'}</button>
        </div></td>` : '<td></td>'}
      </tr>`).join('');
}

async function toggleEmp(id) {
  const r = await api(`/api/employees/${id}/toggle`, 'POST');
  if (r.ok) { await loadEmployees(); toast('Status ပြောင်းပြီးပါပြီ ✅'); }
}

function editEmp(id) {
  const e = EMPS.find(x=>x.id===id);
  if (!e) return;
  EDIT_EMP_ID = id;
  $('modal-emp-title').textContent = '✏️ ဝန်ထမ်း ပြင်ဆင်ရန်';
  $('e-name').value   = e.name||'';
  $('e-email').value  = e.email||'';
  $('e-phone').value  = e.phone||'';
  $('e-dept').value   = e.department||'';
  $('e-pos').value    = e.position||'';
  $('e-salary').value = e.salary||'';
  $('e-join').value   = e.join_date||'';
  $('e-status').value = e.status||'active';
  openModal('emp');
}

async function saveEmployee() {
  const data = {
    name:$('e-name').value, email:$('e-email').value,
    phone:$('e-phone').value, department:$('e-dept').value,
    position:$('e-pos').value, salary:$('e-salary').value,
    join_date:$('e-join').value, status:$('e-status').value,
  };
  if (!data.name||!data.email) { toast('Name/Email ဖြည့်ပါ','err'); return; }
  let r;
  if (EDIT_EMP_ID) r = await api(`/api/employees/${EDIT_EMP_ID}`, 'PUT', data);
  else r = await api('/api/employees', 'POST', data);
  if (r.ok) { closeModal(); await loadEmployees(); toast('ဝန်ထမ်းစာရင်း သိမ်းပြီးပါပြီ ✅'); }
  else toast(r.msg||'Error','err');
}

// ── Leave ──────────────────────────────
async function loadLeaves() {
  const data = await api('/api/leaves');
  LEAVES = data;
  renderLeaves();
}

function setLeaveTab(tab, el) {
  LEAVE_TAB = tab;
  document.querySelectorAll('#p-leave .tab').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
  renderLeaves();
}

function renderLeaves() {
  const filtered = LEAVE_TAB==='all' ? LEAVES : LEAVES.filter(l=>l.status===LEAVE_TAB);
  const showAction = can('approve_leave');
  $('leave-body').innerHTML = filtered.length===0 ?
    `<tr><td colspan="6" class="empty">📋 မှတ်တမ်းမရှိပါ</td></tr>` :
    filtered.map(l=>`
      <tr>
        <td class="td-name">${l.employee_name}</td>
        <td><span class="badge b-${l.leave_type}">${l.leave_type}</span></td>
        <td style="font-size:11px">${l.start_date} → ${l.end_date}</td>
        <td style="font-size:11px;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${l.reason}</td>
        <td>${statusBadge(l.status)}</td>
        ${showAction ? `<td>${l.status==='pending' ? `<div class="btn-row">
          <button class="btn btn-success btn-sm" onclick="updateLeave(${l.id},'approved')">✅ ခွင့်ပြု</button>
          <button class="btn btn-danger btn-sm" onclick="updateLeave(${l.id},'rejected')">❌ ပယ်ချ</button>
        </div>` : `<span style="font-size:11px;color:var(--hint)">ဆောင်ရွက်ပြီး</span>`}</td>` : '<td></td>'}
      </tr>`).join('');
}

async function saveLeave() {
  const data = {
    leave_type:$('l-type').value,
    start_date:$('l-start').value,
    end_date:$('l-end').value,
    reason:$('l-reason').value,
  };
  if (!data.start_date||!data.end_date||!data.reason) { toast('အချက်အလက် ဖြည့်ပါ','err'); return; }
  const r = await api('/api/leaves','POST',data);
  if (r.ok) { closeModal(); await loadLeaves(); toast('ခွင့်လျှောက်ပြီးပါပြီ ✅'); }
  else toast(r.msg||'Error','err');
}

async function updateLeave(id, status) {
  const r = await api(`/api/leaves/${id}/status`,'POST',{status});
  if (r.ok) { await loadLeaves(); toast(status==='approved'?'ခွင့်ပြုပြီး ✅':'ပယ်ချပြီး ✅'); }
}

// ── Payroll ────────────────────────────
async function loadPayroll() {
  const data = await api('/api/payroll');
  PAYROLL = data;
  const months = [...new Set(data.map(p=>p.month))].sort().reverse();
  const sel = $('pay-month-filter');
  const cur = sel.value;
  sel.innerHTML = '<option value="all">လအားလုံး</option>' +
    months.map(m=>`<option value="${m}"${m===cur?' selected':''}>${m}</option>`).join('');
  renderPayroll();
  // Fill employee select in modal
  const emps = await api('/api/employees');
  $('p-emp').innerHTML = '<option value="">ဝန်ထမ်း ရွေးချယ်ပါ</option>' +
    emps.filter(e=>e.status==='active').map(e=>`<option value="${e.id}">${e.name}</option>`).join('');
}

function renderPayroll() {
  const month = $('pay-month-filter').value;
  const filtered = month==='all' ? PAYROLL : PAYROLL.filter(p=>p.month===month);
  const total = filtered.reduce((s,p)=>s+(p.net_salary||0),0);
  const bonus = filtered.reduce((s,p)=>s+(p.bonus||0),0);
  $('pay-stats').innerHTML = `
    <div class="stat-card"><div class="stat-icon">💰</div><div class="stat-value" style="font-size:16px">${fmt(total)}</div><div class="stat-label">လစာစုစုပေါင်း</div></div>
    <div class="stat-card"><div class="stat-icon">👥</div><div class="stat-value">${filtered.length}</div><div class="stat-label">ဝန်ထမ်းဦးရေ</div></div>
    <div class="stat-card"><div class="stat-icon">🎁</div><div class="stat-value" style="font-size:16px">${fmt(bonus)}</div><div class="stat-label">ဘောနပ်စုစုပေါင်း</div></div>
  `;
  $('pay-body').innerHTML = filtered.length===0 ?
    `<tr><td colspan="7" class="empty">💰 မှတ်တမ်းမရှိပါ</td></tr>` :
    filtered.map(p=>`
      <tr>
        <td class="td-name">${p.employee_name}</td>
        <td>${p.month}</td>
        <td>${fmt(p.basic_salary)}</td>
        <td style="color:var(--green)">+${fmt(p.bonus)}</td>
        <td style="color:var(--red)">-${fmt(p.deduction)}</td>
        <td class="money">${fmt(p.net_salary)}</td>
        <td style="font-size:11px;color:var(--hint)">${p.paid_date||'-'}</td>
      </tr>`).join('');
}

function updateNet() {
  const b = parseFloat($('p-basic').value)||0;
  const bo= parseFloat($('p-bonus').value)||0;
  const d = parseFloat($('p-ded').value)||0;
  $('net-show').textContent = fmt(b+bo-d);
}

async function savePayroll() {
  const data = {
    employee_id: $('p-emp').value,
    month:       $('p-month').value,
    basic_salary:parseFloat($('p-basic').value)||0,
    bonus:       parseFloat($('p-bonus').value)||0,
    deduction:   parseFloat($('p-ded').value)||0,
  };
  if (!data.employee_id||!data.month||!data.basic_salary) { toast('အချက်အလက် ဖြည့်ပါ','err'); return; }
  const r = await api('/api/payroll','POST',data);
  if (r.ok) { closeModal(); await loadPayroll(); toast('လစာ သိမ်းပြီးပါပြီ ✅'); }
  else toast(r.msg||'Error','err');
}

// ── Reports ────────────────────────────
async function loadReports() {
  if (!can('view_reports')) { $('reports-content').innerHTML='<div class="denied"><div class="denied-icon">🔒</div>ဝင်ရောက်ခွင့် မရှိပါ</div>'; return; }
  const d = await api('/api/reports');
  if (!d.ok && d.ok===false) return;
  const maxDept = Math.max(...d.dept_data.map(x=>x.cnt), 1);

  let deptHtml = d.dept_data.map(dep=>`
    <div style="margin-bottom:14px">
      <div style="display:flex;justify-content:space-between;margin-bottom:5px">
        <span style="font-size:12px;font-weight:600;color:var(--text)">${dep.department}</span>
        <span style="font-size:11px;color:var(--muted)">${dep.cnt} ဦး · ${fmt(dep.total_sal)}</span>
      </div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.round((dep.cnt/maxDept)*100)}%"></div></div>
    </div>`).join('');

  let earnerHtml = d.top_earners.map(e=>`
    <tr><td class="td-name">${e.name}</td>
    <td style="font-size:11px">${e.department}</td>
    <td class="money">${fmt(e.salary)}</td></tr>`).join('');

  let payHtml = d.pay_data.map(p=>`
    <tr><td class="td-name">${p.month}</td>
    <td class="money">${fmt(p.total)}</td>
    <td style="font-size:11px;color:var(--muted)">${p.cnt} ဦး</td></tr>`).join('');

  $('reports-content').innerHTML = `
    <div class="report-grid">
      <div class="table-card">
        <div class="table-header"><span class="table-title">📊 ဌာနအလိုက် ဝန်ထမ်း</span></div>
        <div style="padding:16px">${deptHtml}</div>
      </div>
      <div class="table-card">
        <div class="table-header"><span class="table-title">💰 လစာ Ranking</span></div>
        <table><thead><tr><th>ဝန်ထမ်း</th><th>ဌာန</th><th>လစာ</th></tr></thead>
        <tbody>${earnerHtml}</tbody></table>
      </div>
    </div>
    <div class="table-card" style="margin-top:14px">
      <div class="table-header"><span class="table-title">📅 လစဉ် လစာ ထုတ်ပေးမှု</span></div>
      <table><thead><tr><th>လ</th><th>လစာစုစုပေါင်း</th><th>ဝန်ထမ်းဦးရေ</th></tr></thead>
      <tbody>${payHtml}</tbody></table>
    </div>`;
}

// ── Roles ──────────────────────────────
async function loadRoles() {
  if (!can('manage_roles')) { $('roles-body').innerHTML='<tr><td colspan="5" class="empty">🔒 ဝင်ရောက်ခွင့် မရှိပါ</td></tr>'; return; }
  const users = await api('/api/users');
  $('roles-body').innerHTML = users.map(u=>`
    <tr>
      <td class="td-name">${u.name}</td>
      <td style="font-size:11px;color:var(--muted)">${u.email}</td>
      <td style="font-size:11px">${u.department||'-'}</td>
      <td>${badge(u.role)}</td>
      <td>
        <select style="background:#0c0e18;border:1px solid var(--border2);color:var(--text);padding:5px 8px;border-radius:6px;font-size:11px;font-family:'DM Sans',sans-serif" onchange="changeRole(${u.id},this.value)">
          <option value="super_admin"${u.role==='super_admin'?' selected':''}>⭐ Super Admin</option>
          <option value="hr_manager"${u.role==='hr_manager'?' selected':''}>🔵 HR Manager</option>
          <option value="employee"${u.role==='employee'?' selected':''}>🟢 Employee</option>
        </select>
      </td>
    </tr>`).join('');
}

async function changeRole(uid, role) {
  const r = await api(`/api/users/${uid}/role`,'POST',{role});
  if (r.ok) { toast('Role ပြောင်းပြီးပါပြီ ✅'); await loadRoles(); }
}

// ── Modals ─────────────────────────────
function openModal(type) {
  closeModal();
  EDIT_EMP_ID = null;
  if (type==='emp') {
    $('modal-emp-title').textContent = '＋ ဝန်ထမ်းအသစ် ထည့်ရန်';
    ['e-name','e-email','e-phone','e-pos','e-salary','e-join'].forEach(id=>$(id).value='');
    $('e-dept').value=''; $('e-status').value='active';
  }
  if (type==='leave') { $('l-start').value=''; $('l-end').value=''; $('l-reason').value=''; }
  if (type==='payroll') { $('p-emp').value=''; $('p-month').value=''; $('p-basic').value=''; $('p-bonus').value=0; $('p-ded').value=0; $('net-show').textContent='K 0'; }
  if (type==='announce') { $('ann-title').value=''; $('ann-body').value=''; }
  $('modal-'+type).classList.remove('hidden');
  $('modal-overlay').classList.remove('hidden');
}

function closeModal() {
  $('modal-overlay').classList.add('hidden');
  document.querySelectorAll('.modal').forEach(m=>m.classList.add('hidden'));
  EDIT_EMP_ID = null;
}

async function saveAnnouncement() {
  const data = {title:$('ann-title').value, body:$('ann-body').value};
  if (!data.title) { toast('ခေါင်းစဉ် ဖြည့်ပါ','err'); return; }
  const r = await api('/api/announcements','POST',data);
  if (r.ok) { closeModal(); await loadDashboard(); toast('ကြေညာချက် ထုတ်ပြန်ပြီးပါပြီ ✅'); }
}

// ── Start ──────────────────────────────
checkSession();
</script>
</body>
</html>"""

if __name__ == "__main__":
    print("\n" + "═"*56)
    print("  🏢  Myanmar HR System — Supabase Edition")
    print("═"*56)
    print("  export SUPABASE_URL=https://xxx.supabase.co")
    print("  export SUPABASE_SERVICE_KEY=your_service_key")
    print("  export SECRET_KEY=any_random_string")
    print("  URL : http://localhost:5000")
    print("═"*56 + "\n")
    app.run(debug=True, port=5000)
