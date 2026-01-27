from flask import Flask, request, jsonify, Response
from werkzeug.utils import secure_filename
import os
from datetime import datetime

app = Flask(__name__)

UPLOAD_FOLDER = "imported_data"
ALLOWED_EXTENSIONS = {"csv"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def timestamped_filename(original_name):
    name, ext = os.path.splitext(original_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{name}_{timestamp}{ext}"


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
  font-family: Arial, sans-serif;
  background: #f4f4f4;
  margin: 0;
  padding: 0;
}

.container {
  display: flex;
  height: 100vh;
}

/* LEFT SIDE */
.left {
  width: 40%;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 40px;
  box-shadow: 2px 0 10px rgba(0,0,0,0.1);
}

.dropzone {
  width: 100%;
  max-width: 350px;
  height: 200px;
  border: 3px dashed #666;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  font-size: 18px;
  color: #666;
  cursor: pointer;
}

.dropzone.dragover {
  border-color: #00aaff;
  background: #e6f7ff;
}

button {
  margin-top: 15px;
  width: 100%;
  max-width: 350px;
  padding: 10px;
}

#message {
  margin-top: 15px;
  font-weight: bold;
  text-align: center;
}

.success { color: green; }
.error { color: red; }

/* RIGHT SIDE */
.right {
  width: 60%;
  padding: 60px;
}

.right h2 {
  margin-top: 0;
}
</style>
</head>
<body>

<div class="container">

  <!-- LEFT: UPLOAD -->
  <div class="left">
    <h2>Upload CSV</h2>

    <div id="dropzone" class="dropzone">
      Drop CSV file here<br>or click to select
    </div>

    <input type="file" id="fileInput" accept=".csv" hidden>
    <button onclick="uploadFile()">Upload</button>

    <div id="message"></div>
  </div>

  <!-- RIGHT: EXPLANATION -->
  <div class="right">
    <h2>How to uplade file</h2>
    <p>
      How to uplade file
    </p>
  </div>

</div>

<script>
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const messageDiv = document.getElementById("message");
let selectedFile = null;

dropzone.onclick = () => fileInput.click();

fileInput.onchange = (e) => {
  selectedFile = e.target.files[0];
  dropzone.innerHTML = "Selected: " + selectedFile.name;
};

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

function uploadFile() {
  messageDiv.innerHTML = "";
  messageDiv.className = "";

  if (!selectedFile) {
    messageDiv.innerHTML = "No file selected";
    messageDiv.className = "error";
    return;
  }

  let formData = new FormData();
  formData.append("file", selectedFile);

  fetch("/upload", {
    method: "POST",
    body: formData
  })
  .then(res => res.json())
  .then(data => {
    if (data.error) {
      messageDiv.innerHTML = data.error;
      messageDiv.className = "error";
    } else {
      messageDiv.innerHTML = "✅ Upload successful: " + data.filename;
      messageDiv.className = "success";
      dropzone.innerHTML = "Drop another CSV file here";
      selectedFile = null;
    }
  })
  .catch(() => {
    messageDiv.innerHTML = "Upload failed";
    messageDiv.className = "error";
  });
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
        return jsonify({"error": "Only CSV files are allowed"}), 400

    safe_name = secure_filename(file.filename)
    new_name = timestamped_filename(safe_name)

    path = os.path.join(app.config["UPLOAD_FOLDER"], new_name)
    file.save(path)

    return jsonify({
        "message": "Upload successful",
        "filename": new_name
    })
