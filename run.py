from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from utils.functions import csv_handler, filter_trades
from zoneinfo import ZoneInfo
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
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===== HELPERS =====
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ===== AUTH =====
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.post("/auth/session")
def auth_session():
    data         = request.json
    access_token = data.get("access_token")

    if not access_token:
        return jsonify({"error": "No token"}), 400

    try:
        # Tell Supabase to use this token and get the user from it
        user = supabase.auth.get_user(access_token)
        session["user"] = {
            "id":    user.user.id,
            "email": user.user.email
        }
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 401

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email    = request.form["email"]
        password = request.form["password"]
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            session["user"] = {"id": res.user.id, "email": res.user.email}
            return redirect(url_for("dashboard"))
        except Exception:
            return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")


@app.route("/auth/google")
def auth_google():
    res = supabase.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {"redirect_to": "http://localhost:5000/auth/callback"}
    })
    return redirect(res.url)


@app.route("/auth/callback")
def auth_callback():
    return render_template("auth_callback.html")


@app.route("/logout")
def logout():
    session.clear()
    supabase.auth.sign_out()
    return redirect(url_for("login"))


# ===== CHART GENERATION =====
def generate_chart_base64(symbol, entry_time, exit_time, entry_price, exit_price, side):
    try:
        yahoo_symbol = symbol if symbol.endswith("=F") else f"{symbol}=F"
        trade_date   = entry_time.date()

        period1 = int((datetime.combine(trade_date, datetime.min.time()) - timedelta(days=1)).timestamp())
        period2 = int((datetime.combine(trade_date, datetime.min.time()) + timedelta(days=2)).timestamp())

        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
            f"?interval=5m&period1={period1}&period2={period2}"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept":     "application/json",
            "Referer":    "https://finance.yahoo.com",
        }

        r = requests.get(url, headers=headers, timeout=10)
        if not r.ok:
            print(f"Yahoo returned {r.status_code} for {yahoo_symbol}")
            return None

        data      = r.json()
        result    = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote     = result["indicators"]["quote"][0]

        df = pd.DataFrame({
            "Open":   quote["open"],
            "High":   quote["high"],
            "Low":    quote["low"],
            "Close":  quote["close"],
            "Volume": quote.get("volume", [0] * len(timestamps))
        }, index=pd.to_datetime(timestamps, unit="s", utc=True).tz_convert("Europe/Paris"))

        df = df.dropna()
        if df.empty:
            print(f"Empty DataFrame for {yahoo_symbol}")
            return None

        entry_ts = pd.Timestamp(entry_time).tz_localize(ZoneInfo("Europe/Paris"))
        exit_ts  = pd.Timestamp(exit_time).tz_localize(ZoneInfo("Europe/Paris"))

        df = df[
            (df.index >= entry_ts - timedelta(hours=2)) &
            (df.index <= exit_ts  + timedelta(hours=2))
        ]
        if df.empty:
            print(f"No candles in trade window for {yahoo_symbol}")
            return None

        is_long     = str(side).lower() == "long"
        entry_color = "green" if is_long else "red"
        exit_color  = "red"   if is_long else "green"

        entry_idx = df.index.get_indexer([entry_ts], method="nearest")[0]
        exit_idx  = df.index.get_indexer([exit_ts],  method="nearest")[0]

        apds = [
            mpf.make_addplot(
                [entry_price if i == entry_idx else float("nan") for i in range(len(df))],
                type="scatter", markersize=120,
                marker="^" if is_long else "v",
                color=entry_color
            ),
            mpf.make_addplot(
                [exit_price if i == exit_idx else float("nan") for i in range(len(df))],
                type="scatter", markersize=120,
                marker="v" if is_long else "^",
                color=exit_color
            ),
        ]

        hlines = dict(
            hlines=[entry_price, exit_price],
            colors=[entry_color, exit_color],
            linestyle="--",
            linewidths=1
        )

        buf = io.BytesIO()
        mpf.plot(
            df,
            type="candle",
            style="charles",
            addplot=apds,
            hlines=hlines,
            tight_layout=True,
            savefig=dict(fname=buf, format="png", dpi=100),
            figsize=(10, 5)
        )
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    except Exception as e:
        print(f"Chart generation failed for {symbol}: {e}")
        return None


# ===== PAGE ROUTES =====

@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/journal")
@login_required
def journal():
    return render_template("journal.html")


@app.route("/charts")
@login_required
def charts():
    return render_template("charts.html")


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload_file():
    if request.method == "GET":
        return render_template("upload.html")

    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if not file.filename.lower().endswith(".csv"):
            return jsonify({"error": "Only CSV files allowed"}), 400

        account_id = request.form.get("account_id")
        if not account_id:
            return jsonify({"error": "No account selected"}), 400

        df = pd.read_csv(file)
        df_imported_trades = csv_handler(df)
        df_imported_trades["key_trading_accounts"] = account_id

        data    = df_imported_trades.to_dict(orient="records")
        columns = list(df_imported_trades.columns)

        df_imported_trades["entryTimestamp"] = df_imported_trades["entryTimestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        df_imported_trades["exitTimestamp"]  = df_imported_trades["exitTimestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

        records  = df_imported_trades.to_dict(orient="records")
        response = supabase.table("trades").insert(records).execute()

        inserted_trades = response.data or []
        print(f"Inserted {len(inserted_trades)} trades, generating charts...")

        for trade in inserted_trades:
            try:
                chart_b64 = generate_chart_base64(
                    symbol      = trade["symbol"],
                    entry_time  = datetime.fromisoformat(trade["entryTimestamp"]),
                    exit_time   = datetime.fromisoformat(trade["exitTimestamp"]),
                    entry_price = float(trade["entryPrice"]),
                    exit_price  = float(trade["exitPrice"]),
                    side        = trade["side"]
                )
                if chart_b64:
                    supabase.table("trades").update({"chart_image": chart_b64}).eq("id", trade["id"]).execute()
                    print(f"Chart saved for trade {trade['id']}")
                else:
                    print(f"No chart generated for trade {trade['id']} ({trade['symbol']})")
            except Exception as e:
                print(f"Chart generation failed for trade {trade.get('id')}: {e}")
                continue

        return jsonify({"rows": data, "columns": columns})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/accounts")
@login_required
def settings():
    return render_template("settings.html")


# ===== API ROUTES =====

@app.get("/api/trades")
@login_required
def api_trades():
    try:
        account_id  = request.args.get("account")
        date_from   = request.args.get("from")
        date_to     = request.args.get("to")
        strategy_id = request.args.get("strategy")
        setup_ids   = request.args.getlist("setups")

        trades_res = supabase.table("trades").select("*").execute()
        trades     = trades_res.data or []

        if not trades:
            return jsonify([])

        trade_ids = [t["id"] for t in trades]

        links_res = (
            supabase.table("trade_setup")
            .select("key_trade_id, key_setup_id")
            .in_("key_trade_id", trade_ids)
            .execute()
        )
        links = links_res.data or []

        setups_by_trade = {}
        for l in links:
            setups_by_trade.setdefault(l["key_trade_id"], []).append(l["key_setup_id"])

        for t in trades:
            t["setups"] = setups_by_trade.get(t["id"], [])

        trades = filter_trades(
            trades,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            strategy_id=strategy_id,
            setup_ids=setup_ids,
        )
        return jsonify(trades)

    except Exception as e:
        print("api/trades error:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/yahoo/<symbol>")
@login_required
def fetch_yahoo(symbol):
    try:
        yahoo_symbol = symbol if symbol.endswith("=F") else f"{symbol}=F"
        date_str     = request.args.get("date")
        interval     = request.args.get("interval", "5m")
        range_param  = request.args.get("range", None)

        if date_str:
            trade_date = datetime.strptime(date_str, "%Y-%m-%d")
            period1    = int((trade_date - timedelta(days=1)).timestamp())
            period2    = int((trade_date + timedelta(days=1)).timestamp())
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
                f"?interval={interval}&period1={period1}&period2={period2}"
            )
        else:
            r = range_param or "1d"
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
                f"?interval={interval}&range={r}"
            )

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept":     "application/json",
            "Referer":    "https://finance.yahoo.com",
        }

        r = requests.get(url, headers=headers, timeout=10)
        if not r.ok:
            return jsonify({"error": r.status_code, "body": r.text[:500]}), 502

        return jsonify(r.json())

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.delete("/api/trades")
@login_required
def delete_trades():
    data = request.json
    ids  = data.get("ids", [])

    if not ids:
        return {"error": "No IDs provided"}, 400

    supabase.table("trade_setup").delete().in_("key_trade_id", ids).execute()
    supabase.table("trades").delete().in_("id", ids).execute()
    return {"deleted": len(ids)}


@app.get("/api/accounts")
@login_required
def get_accounts():
    response = supabase.table("trading_accounts").select("id, name").order("created_at").execute()
    return jsonify(response.data or [])


@app.post("/api/accounts")
@login_required
def add_account():
    data = request.json
    supabase.table("trading_accounts").insert(data).execute()
    return {"ok": True}


@app.delete("/api/accounts/<id>")
@login_required
def delete_account(id):
    supabase.table("trading_accounts").delete().eq("id", id).execute()
    return {"ok": True}


@app.patch("/api/trades/<id>")
@login_required
def update_trade(id):
    data     = request.json
    response = supabase.table("trades").update(data).eq("id", id).execute()

    if response.data is None:
        return {"error": "Update failed"}, 400
    return {"ok": True}


@app.get("/api/strategies")
@login_required
def get_strategies():
    try:
        response = supabase.table("strategies").select("id, strategy_name, color").order("strategy_name").execute()
        return jsonify(response.data or [])
    except Exception as e:
        print("Supabase /api/strategies error:", e)
        return jsonify({"error": str(e)}), 500


@app.get("/api/setups")
@login_required
def get_setups():
    response = supabase.table("setups").select("id, setup_name, color").order("setup_name").execute()
    return jsonify(response.data or [])


@app.post("/api/trade_setup")
@login_required
def add_trade_setup():
    data     = request.json
    response = supabase.table("trade_setup").insert({
        "key_trade_id": data["key_trade_id"],
        "key_setup_id": data["key_setup_id"]
    }).execute()
    return jsonify(response.data[0])


@app.get("/api/trade_setups")
@login_required
def get_trade_setups():
    try:
        response = supabase.table("trade_setup").select("*").execute()
        return jsonify(response.data or [])
    except Exception as e:
        print("Supabase /api/trade_setups error:", e)
        return jsonify({"error": str(e)}), 500


@app.delete("/api/trade_setups")
@login_required
def delete_trade_setup():
    data     = request.json
    trade_id = data.get("trade_id")
    setup_id = data.get("setup_id")

    if not trade_id or not setup_id:
        return {"error": "Missing trade_id or setup_id"}, 400

    supabase.table("trade_setup").delete().eq("key_trade_id", trade_id).eq("key_setup_id", setup_id).execute()
    return {"ok": True}


# ===== ENTRY POINT =====
if __name__ == "__main__":
    app.run(debug=True)