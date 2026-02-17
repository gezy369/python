from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime
from utils.functions import csv_handler
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
        # Fetch all trades
        trades_res = supabase.table("trades").select("*").execute()
        trades = trades_res.data or []

        if not trades:
            return jsonify([])

        trade_ids = [t["id"] for t in trades]

        # Fetch trade_setup links for all trades
        links_res = (
            supabase.table("trade_setup")
            .select("key_trade_id, key_setup_id")
            .in_("key_trade_id", trade_ids)
            .execute()
        )
        links = links_res.data or []

        # Attach setups to trades
        setups_by_trade = {}
        for l in links:
            setups_by_trade.setdefault(l["key_trade_id"], []).append(l["key_setup_id"])

        for t in trades:
            t["setups"] = setups_by_trade.get(t["id"], [])

        return jsonify(trades)

    except Exception as e:
        print("api/trades error:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/charts")
def charts():

    return render_template("charts.html")

# ===== TRADES UPLOAD =====
@app.route("/upload", methods=["GET", "POST"])
def upload_file():
    if request.method == "GET":
        return render_template("upload.html")
    
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]

        if not file.filename.lower().endswith(".csv"):
            return jsonify({"error": "Only CSV files allowed"}), 400

        # Read CSV directly into pandas DataFrame
        df = pd.read_csv(file)  # <- file is already a file-like object

        # Pass DataFrame to your function
        df_imported_trades = csv_handler(df)
        
        # Convert DataFrame to JSON-safe format
        data = df_imported_trades.to_dict(orient="records")
        columns = list(df_imported_trades.columns)

        # Insert into Supabase
        # Convert timestamps to strings for JSON / Supabase
        df_imported_trades["entryTimestamp"] = df_imported_trades["entryTimestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        df_imported_trades["exitTimestamp"] = df_imported_trades["exitTimestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        # Convert DataFrame to list of dicts
        records = df_imported_trades.to_dict(orient="records")

        # Insert into Supabase
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
    # Join trade_setup with setups to get name & color
    response = (
        supabase
        .table("trade_setup")
        .select("""
            id,                 # trade_setup id
            key_trade_id,
            key_setup_id,
            setups!key_setup_id (
                id,
                setup_name,
                color
            )
        """)
        .execute()
    )

    rows = []
    for r in response.data or []:
        rows.append({
            "trade_setup_id": r["id"],
            "key_trade_id": r["key_trade_id"],
            "key_setup_id": r["key_setup_id"],
            "setup_name": r["setups"]["setup_name"],
            "color": r["setups"]["color"]
        })

    return jsonify(rows)



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