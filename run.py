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
@app.route("/api/trades")
def api_trades():
    try:
        response = supabase.table("trades").select("*").execute()
        
        # Check if the API returned data
        if hasattr(response, "data") and response.data is not None:
            rows = response.data
        else:
            rows = []
        
        return jsonify(rows)
    
    except Exception as e:
        print("Supabase API error:", e)
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

    Trade.query.filter(Trade.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()

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
    supabase.table("trades").update(request.json).eq("id", id).execute()
    return {"ok": True}

@app.delete("/api/accounts/<id>")
def delete_account(id):
    supabase.table("trading_accounts") \
        .delete() \
        .eq("id", id) \
        .execute()
    return {"ok": True}




# ===== ENTRY POINT =====
if __name__ == "__main__":
    app.run(debug=True)