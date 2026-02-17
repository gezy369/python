from flask import Flask, render_template, request, jsonify
from utils.functions import csv_handler
import os
import pandas as pd
from supabase import create_client, Client

app = Flask(__name__)

# ===== CONFIG =====
UPLOAD_FOLDER = "imported_data"
ALLOWED_EXTENSIONS = {"csv"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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

@app.route("/api/trades")
def api_trades():
    response = supabase.table("trades").select("*").execute()
    return jsonify(response.data or [])

@app.delete("/api/trades")
def delete_trades():
    ids = request.json.get("ids", [])
    if not ids:
        return {"error": "No IDs provided"}, 400

    supabase.table("trades").delete().in_("id", ids).execute()
    return {"deleted": len(ids)}

@app.patch("/api/trades/<id>")
def update_trade(id):
    data = request.json
    supabase.table("trades").update(data).eq("id", id).execute()
    return {"ok": True}

@app.get("/api/strategies")
def get_strategies():
    response = (
        supabase.table("strategies")
        .select("id, strategy_name, color")
        .order("strategy_name")
        .execute()
    )
    return jsonify(response.data or [])

@app.get("/api/setups")
def get_setups():
    response = (
        supabase.table("setups")
        .select("id, setup_name, color")
        .order("setup_name")
        .execute()
    )
    return jsonify(response.data or [])

if __name__ == "__main__":
    app.run(debug=True)
