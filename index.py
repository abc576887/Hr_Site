import os, hashlib, secrets
from datetime import date
from functools import wraps
from flask import Flask, request, jsonify, session, make_response
from supabase import create_client

app = Flask(__name__)
# Vercel Environment Variables မှ Key များယူခြင်း
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

def sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def pw(p):
    return hashlib.sha256(p.encode()).hexdigest()

# Roles & Permissions
PERMS = {
    "super_admin": dict(view_all=True, manage_emp=True, approve_leave=True, manage_payroll=True),
    "hr_manager":  dict(view_all=True, manage_emp=True, approve_leave=True, manage_payroll=True),
    "employee":    dict(view_all=False, manage_emp=False, approve_leave=False, manage_payroll=False),
}

def current_user(): return session.get("user")

# --- API Routes ---
@app.route("/api/login", methods=["POST"])
def api_login():
    d = request.json or {}
    try:
        r = sb().table("users").select("*").eq("email", d.get("email", "")).eq("password", pw(d.get("password", ""))).execute()
        if not r.data:
            return jsonify({"ok": False, "msg": "Email သို့မဟုတ် Password မှားယွင်းနေပါသည်"})
        session["user"] = r.data[0]
        return jsonify({"ok": True, "user": r.data[0]})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/")
@app.route("/login")
def index():
    return make_response(HTML)

# --- Frontend HTML (Login UI အပါအဝင်) ---
HTML = r"""<!DOCTYPE html>
<html lang="my">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Myanmar HR System</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f4f7f6; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: white; padding: 40px; border-radius: 10px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); width: 350px; text-align: center; }
        h2 { color: #333; margin-bottom: 25px; }
        input { width: 100%; padding: 12px; margin-bottom: 20px; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box; }
        button { width: 100%; padding: 12px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        button:hover { background: #0056b3; }
        #error-msg { color: #dc3545; margin-top: 15px; font-size: 14px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>HR System Login</h2>
        <input type="email" id="email" placeholder="Email (admin@hr.com)">
        <input type="password" id="password" placeholder="Password">
        <button onclick="handleLogin()">Login</button>
        <div id="error-msg"></div>
    </div>

    <script>
        async function handleLogin() {
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const errorDiv = document.getElementById('error-msg');
            
            errorDiv.innerText = "ခေတ္တစောင့်ဆိုင်းပါ...";

            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();
            
            if (data.ok) {
                alert("Login အောင်မြင်ပါသည်။ Dashboard သို့ ပို့ဆောင်ပေးနေပါသည်...");
                // Dashboard Link သို့သွားရန် ဤနေရာတွင် ပြင်နိုင်သည်
            } else {
                errorDiv.innerText = data.msg;
            }
        }
    </script>
</body>
</html>
"""
