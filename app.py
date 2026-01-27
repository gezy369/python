from flask import Flask, jsonify
import pandas as pd
import os

app = Flask(__name__)

@app.route("/home")
return "My new website"

# reads the CSV file and the URL is /data
@app.route("/data")
def data():
    csv_path = os.path.join("imported_data", "Orders.csv")
    df = pd.read_csv(csv_path)
    return jsonify(df.to_dict(orient="records"))
