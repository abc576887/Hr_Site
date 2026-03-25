import os, hashlib, secrets
from datetime import date
from functools import wraps
from flask import Flask, request, jsonify, session, make_response
from supabase import create_client

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# Supabase Config
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

def sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def pw(p):
    return hashlib.sha256(p.encode()).hexdigest()

# Roles & Permissions
PERMS = {
    "super_admin": dict(view_all=True,manage_emp=True,approve_leave=True,manage_payroll=True,manage_roles=True,view_reports=True),
    "hr_manager":  dict(view_all=True,manage_emp=True,approve_leave=True,manage_payroll=True,manage_roles=False,view_reports=True),
    "employee":    dict(view_all=False,manage_emp=False,approve_leave=False,manage_payroll=False,manage_roles=False,view_reports=False),
}

def current_user(): return session.get("user")
def can(p): u=current_user(); return bool(u and PERMS.get(u.get("role"),{}).get(p,False))

def login_required(f):
    @wraps(f)
    def d(*a,**kw):
        if not current_user(): return jsonify({"ok":False,"msg":"Login မဝင်ရသေးပါ"}),401
        return f(*a,**kw)
    return d

# --- API Routes ---
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

# (အခြား API routes များ ဒီကြားထဲမှာ ရှိပါမည်...)

@app.route("/")
@app.route("/login")
def index():
    return make_response(HTML)

# --- Frontend HTML ---
HTML = r"""<!DOCTYPE html>
<html lang="my">
<head>
    <meta charset="UTF-8">
    <title>Myanmar HR System</title>
    </head>
<body>
    <div id="app">
        </div>
    </body>
</html>
""" # ဒီနေရာမှာ သေချာ ပိတ်ပေးရပါမယ်
