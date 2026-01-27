from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

# Variables
UPLOAD_FOLDER = "imported_data"
ALLOWED_EXTENSIONS = {"csv"}

# 
@app.route("/")
def home():
    return "Home of my journal"


# reads the CSV file and the URL is /data
@app.route("/data")
def data():
    csv_path = os.path.join("imported_data", "Orders.csv")
    df = pd.read_csv(csv_path)
    return jsonify(df.to_dict(orient="records"))





app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


@app.route("/upload", methods=["POST"])
def upload_csv():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Only CSV files are allowed"}), 400

    filename = secure_filename(file.filename)
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    file.save(save_path)

    return jsonify({
        "message": "File uploaded successfully",
        "filename": filename
    }), 200
