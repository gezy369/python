from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime
import os

app = Flask(__name__)

# ===== CONFIG =====
UPLOAD_FOLDER = "imported_data"
ALLOWED_EXTENSIONS = {"csv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ===== HELPERS =====
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ===== ROUTES =====

@app.route("/")
def dashboard():
    return render_template("dashboard.html")

@app.route("/upload", methods=["GET"])
def upload_page():
    return render_template("upload.html")

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"})

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"})

    if not allowed_file(file.filename):
        return jsonify({"error": "Only CSV files are allowed"})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = secure_filename(file.filename)
    new_filename = f"{timestamp}_{filename}"

    save_path = os.path.join(app.config["UPLOAD_FOLDER"], new_filename)
    file.save(save_path)

    return jsonify({
        "message": "Upload successful",
        "filename": new_filename
    })

# ===== ENTRY POINT =====
if __name__ == "__main__":
    app.run(debug=True)
