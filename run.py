from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime
from utils.functions import csv_handler, filter_trades
import os
import io
import pandas as pd
from supabase import create_client, Client

app = Flask(__name__)

# ===== CONFIG =====
UPLOAD_FOLDER = "imported_data"
ALLOWED_EXTENSIONS = {"csv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ===== HELPERS =====

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ===== SUPABASE CONFIG =====

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ===== ROUTES =====

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/journal")
def journal():
    return render_template("journal.html")

# Fetch all the trades in the DB
@app.get("/api/trades")
def api_trades():
    
    try:
        # ---------- QUERY PARAMS ----------
        account_id = request.args.get("account")
        date_from = request.args.get("from")
        date_to = request.args.get("to")
        strategy_id = request.args.get("strategy")
        setup_ids = request.args.getlist("setups")

        # ---------- FETCH TRADES ----------
        trades_res = supabase.table("trades").select("*").execute()
        trades = trades_res.data or []



        # TEST TEST TEST TEST
        print("FILTER PARAMS:", account_id, date_from, date_to, strategy_id, setup_ids)
        print("TRADES BEFORE:", len(trades))
        # TEST TEST TEST TEST



        if not trades:
            return jsonify([])

        trade_ids = [t["id"] for t in trades]

        # ---------- FETCH SETUPS ----------
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

        # ---------- APPLY SHARED FILTER ----------
        trades = filter_trades(
            trades,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            strategy_id=strategy_id,
            setup_ids=setup_ids,
        )
        print("TRADES AFTER:", len(trades))
        return jsonify(trades)


    except Exception as e:
        print("api/trades error:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/charts")
def charts():

    return render_template("charts.html")
# ===== CHARTING =====
@app.route("/api/yahoo/<symbol>")
def fetch_yahoo(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
    r = requests.get(url)
    r.raise_for_status()
    return jsonify(r.json())


# ===== TRADES UPLOAD =====
@app.route("/upload", methods=["GET", "POST"])
def upload_file():
    if request.method == "GET":
        return render_template("upload.html")
    
    try:
        # ---------- FILE ----------
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]

        if not file.filename.lower().endswith(".csv"):
            return jsonify({"error": "Only CSV files allowed"}), 400

        # ---------- ACCOUNT ----------
        account_id = request.form.get("account_id")
        if not account_id:
            return jsonify({"error": "No account selected"}), 400

        # ---------- READ CSV ----------
        df = pd.read_csv(file)

        # Your existing CSV handler
        df_imported_trades = csv_handler(df)

        # ---------- ADD ACCOUNT TO ALL TRADES ----------
        df_imported_trades["key_trading_accounts"] = account_id

        # ---------- PREVIEW DATA ----------
        data = df_imported_trades.to_dict(orient="records")
        columns = list(df_imported_trades.columns)

        # ---------- FORMAT TIMESTAMPS ----------
        df_imported_trades["entryTimestamp"] = (
            df_imported_trades["entryTimestamp"]
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        )
        df_imported_trades["exitTimestamp"] = (
            df_imported_trades["exitTimestamp"]
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        )

        # ---------- INSERT INTO SUPABASE ----------
        records = df_imported_trades.to_dict(orient="records")
        response = supabase.table("trades").insert(records).execute()

        print(response)

        return jsonify({
            "rows": data,
            "columns": columns
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# ===== TRADES DELETE =====
@app.delete("/api/trades")
def delete_trades():
    data = request.json
    ids = data.get("ids", [])

    if not ids:
        return {"error": "No IDs provided"}, 400

    supabase.table("trades").delete().in_("id", ids).execute()

    return {"deleted": len(ids)}



# ===== SETTINGS =====
@app.route("/accounts")
def settings():

    return render_template("settings.html")

@app.get("/api/accounts")
def get_accounts():
    response = (
        supabase
        .table("trading_accounts")
        .select("id, name")
        .order("created_at")
        .execute()
    )
    return jsonify(response.data or [])

@app.post("/api/accounts")
def add_account():
    data = request.json
    supabase.table("trading_accounts").insert(data).execute()
    return {"ok": True}

@app.patch("/api/trades/<id>")
def update_trade(id):
    data = request.json

    response = (
        supabase
        .table("trades")
        .update(data)
        .eq("id", id)
        .execute()
    )

    if response.data is None:
        return {"error": "Update failed"}, 400

    return {"ok": True}


@app.delete("/api/accounts/<id>")
def delete_account(id):
    supabase.table("trading_accounts") \
        .delete() \
        .eq("id", id) \
        .execute()
    return {"ok": True}

@app.get("/api/strategies")
def get_strategies():
    try:
        response = (
            supabase.table("strategies")
            .select("id, strategy_name, color")   # include color
            .order("strategy_name")              # correct column name
            .execute()
        )
        return jsonify(response.data or [])
    except Exception as e:
        print("Supabase /api/strategies error:", e)
        return jsonify({"error": str(e)}), 500


# ===== TRADE SETUPS =====
@app.get("/api/setups")
def get_setups():
    response = (
        supabase
        .table("setups")
        .select("id, setup_name, color")
        .order("setup_name")
        .execute()
    )
    return jsonify(response.data or [])



@app.post("/api/trade_setup")
def add_trade_setup():
    data = request.json
    response = (
        supabase
        .table("trade_setup")
        .insert({
            "key_trade_id": data["key_trade_id"],
            "key_setup_id": data["key_setup_id"]
        })
        .execute()
    )
    return jsonify(response.data[0])

@app.get("/api/trade_setups")
def get_trade_setups():
    try:
        # fetch all trade_setup links
        response = supabase.table("trade_setup").select("*").execute()
        return jsonify(response.data or [])
    except Exception as e:
        print("Supabase /api/trade_setups error:", e)
        return jsonify({"error": str(e)}), 500




@app.delete("/api/trade_setups")
def delete_trade_setup():
    data = request.json
    trade_id = data.get("trade_id")
    setup_id = data.get("setup_id")

    if not trade_id or not setup_id:
        return {"error": "Missing trade_id or setup_id"}, 400

    supabase.table("trade_setup") \
        .delete() \
        .eq("key_trade_id", trade_id) \
        .eq("key_setup_id", setup_id) \
        .execute()

    return {"ok": True}






# ===== ENTRY POINT =====
if __name__ == "__main__":
    app.run(debug=True)