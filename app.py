from flask import Flask, request, jsonify, Response
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

UPLOAD_FOLDER = "imported_data"
ALLOWED_EXTENSIONS = {"csv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------- HTML PAGE ----------
@app.route("/upload", methods=["GET"])
def upload_page():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Upload CSV</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: #f4f4f4;
                padding: 40px;
            }
            .container {
                background: white;
                padding: 20px;
                max-width: 400px;
                margin: auto;
                border-radius: 6px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }
            button {
                margin-top: 10px;
                padding: 10px;
                width: 100%;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Upload CSV file</h2>
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file" accept=".csv" required>
                <button type="submit">Upload</button>
            </form>
        </div>
    </body>
    </html>
    """
    return Response(html, mimetype="text/html")


# ---------- FILE UPLOAD ----------
@app.route("/upload", methods=["POST"])
def upload_csv():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Only CSV files are allowed"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    return jsonify({
        "message": "File uploaded successfully",
        "filename": filename
    }), 200
