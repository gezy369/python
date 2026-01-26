from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Hello world second time!"

    import csv

    with open("./imported_data/Orders.csv", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            print(row)
