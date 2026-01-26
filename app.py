from flask import Flask, jsonify
import pandas as pd

app = Flask(__name__)

@app.route("/data")
def data():
    df = pd.read_csv("Orders.csv")
    return jsonify(df.to_dict(orient="records"))
