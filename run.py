from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from datetime import datetime, timedelta
from utils.functions import csv_handler, filter_trades
import os
import io, base64
import pandas as pd
from supabase import create_client, Client
import requests
import mplfinance as mpf
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-in-production")

# ===== CONFIG =====
UPLOAD_FOLDER = "imported_data"
ALLOWED_EXTENSIONS = {"csv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ===== SUPABASE =====
SUPABASE_URL         = os.environ.get("SUPABASE_URL")
SUPABASE_KEY         = os.environ.get("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

supabase      : Client = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ===== HELPERS =====

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def load_user_settings_into_session(user_id):
    """Load DB settings into Flask session after login"""
    res = (
        supabase_admin.table("settings")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    settings = (res.data or [{}])[0]

    session["timezone"] = settings.get("timezone", "Europe/Paris")
    session["settings"] = settings


def get_user_trade_ids(user_id):
    accounts_res = (
        supabase_admin.table("trading_accounts")
        .select("id")
        .eq("user_id", user_id)
        .execute()
    )

    account_ids = [a["id"] for a in (accounts_res.data or [])]

    if not account_ids:
        return []

    trades_res = (
        supabase_admin.table("trades")
        .select("id")
        .in_("key_trading_accounts", account_ids)
        .execute()
    )

    return [t["id"] for t in (trades_res.data or [])]


# ===== AUTH =====

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        try:
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            session["user"] = {
                "id": res.user.id,
                "email": res.user.email
            }

            load_user_settings_into_session(res.user.id)

            return redirect(url_for("dashboard"))

        except Exception:
            return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


@app.post("/auth/session")
def auth_session():
    data = request.json
    access_token = data.get("access_token")

    if not access_token:
        return jsonify({"error": "No token"}), 400

    try:
        user = supabase.auth.get_user(access_token)

        session["user"] = {
            "id": user.user.id,
            "email": user.user.email
        }

        load_user_settings_into_session(user.user.id)

        return jsonify({"ok": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 401


@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")

    if not code:
        return redirect(url_for("login"))

    try:
        res = supabase.auth.exchange_code_for_session({
            "auth_code": code
        })

        session["user"] = {
            "id": res.user.id,
            "email": res.user.email
        }

        load_user_settings_into_session(res.user.id)

        return redirect(url_for("dashboard"))

    except Exception as e:
        print("Auth callback error:", e)
        return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ===== SETTINGS API =====

@app.get("/api/settings")
@login_required
def get_settings():
    try:
        user_id = session["user"]["id"]

        res = (
            supabase_admin.table("settings")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )

        return jsonify(res.data[0] if res.data else {})

    except Exception as e:
        print(e)
        return jsonify({})


@app.patch("/api/settings")
@login_required
def update_settings():
    try:
        user_id = session["user"]["id"]
        data = request.json

        existing = (
            supabase_admin.table("settings")
            .select("id")
            .eq("user_id", user_id)
            .execute()
        )

        if existing.data:
            supabase_admin.table("settings") \
                .update(data) \
                .eq("user_id", user_id) \
                .execute()
        else:
            data["user_id"] = user_id
            supabase_admin.table("settings") \
                .insert(data) \
                .execute()

        if "timezone" in data:
            session["timezone"] = data["timezone"]

        session["settings"] = {**session.get("settings", {}), **data}

        return jsonify({"ok": True})

    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500


# ===== DASHBOARD =====

@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/accounts")
@login_required
def settings_page():
    return render_template("settings.html")

@app.post("/api/trades/generate-charts")
@login_required
def generate_charts():
    try:
        data = request.json
        ids = data.get("ids", [])

        if not ids:
            return jsonify({"error": "No trade IDs"}), 400

        trades_res = (
            supabase_admin.table("trades")
            .select("*")
            .in_("id", ids)
            .execute()
        )

        trades = trades_res.data or []
        failed = []

        for trade in trades:
            try:
                chart_b64 = generate_chart_base64(
                    symbol=trade["symbol"],
                    entry_time=datetime.fromisoformat(trade["entryTimestamp"]),
                    exit_time=datetime.fromisoformat(trade["exitTimestamp"]),
                    entry_price=float(trade["entryPrice"]),
                    exit_price=float(trade["exitPrice"]),
                    side=trade["side"]
                )

                if chart_b64:
                    supabase_admin.table("trades") \
                        .update({"chart_image": chart_b64}) \
                        .eq("id", trade["id"]) \
                        .execute()

            except Exception as e:
                print(f"Chart error {trade['id']}: {e}")
                failed.append(trade["id"])

        return jsonify({
            "ok": True,
            "failed": failed
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================================================
# NOTE:
# All other endpoints from your original file remain unchanged
# (trades, accounts, fees, strategies, setups, emotions, etc.)
# =========================================================


if __name__ == "__main__":
    app.run(debug=True)