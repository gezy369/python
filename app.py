from flask import Flask, request, jsonify, Response
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

UPLOAD_FOLDER = "imported_data"
ALLOWED_EXTENSIONS = {"csv"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------- DRAG & DROP PAGE ----------
@app.route("/upload", methods=["GET"])
def upload_page():
    return Response("""
<!DOCTYPE html>
<html>
<head>
<title>Upload CSV</title>
<style>
body {
  font-family: Arial;
  background: #f4f4f4;
  padding: 50px;
}
.dropzone {
  width: 400px;
  height: 200px;
  border: 3px dashed #666;
  border-radius: 10px;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  font-size: 18px;
  color: #666;
  margin: auto;
  cursor: pointer;
}
.dropzone.dragover {
  border-color: #00aaff;
  background: #e6f7ff;
}
button {
  margin-top: 15px;
  width: 100%;
  padding: 10px;
}
</style>
</head>
<body>

<h2 style="text-align:center;">Upload CSV (Drag & Drop)</h2>

<div id="dropzone" class="dropzone">
  Drop CSV file here or click to select
</div>

<input type="file" id="fileInput" accept=".csv" hidden>
<button onclick="uploadFile()">Upload</button>

<script>
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
let selectedFile = null;

// Click to select
dropzone.onclick = () => fileInput.click();
fileInput.onchange = (e) => {
  selectedFile = e.target.files[0];
  dropzone.innerHTML = "Selected: " + selectedFile.name;
};

// Drag events
dropzone.ondragover = (e) => {
  e.preventDefault();
  dropzone.classList.add("dragover");
};
dropzone.ondragleave = () => dropzone.classList.remove("dragover");
dropzone.ondrop = (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  selectedFile = e.dataTransfer.files[0];
  dropzone.innerHTML = "Dropped: " + selectedFile.name;
};

// Upload function
function uploadFile() {
  if (!selectedFile) {
    alert("No file selected");
    return;
  }

  let formData = new FormData();
  formData.append("file", selectedFile);

  fetch("/upload", {
    method: "POST",
    body: formData
  })
  .then(res => res.json())
  .then(data => alert(JSON.stringify(data)))
  .catch(err => alert("Upload failed"));
}
</script>

</body>
</html>
""", mimetype="text/html")


# ---------- UPLOAD HANDLER ----------
@app.route("/upload", methods=["POST"])
def upload_csv():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Only CSV files allowed"}), 400

    filename = secure_filename(file.filename)
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(path)

    return jsonify({"message": "Upload OK", "filename": filename})
