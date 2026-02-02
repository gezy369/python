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
    




# ===== ENTRY POINT =====
if __name__ == "__main__":
    app.run(debug=True)
