from flask import Flask, render_template, request

app = Flask(__name__)

@app.route("/", methods=["POST", "GET"])
def index():
    geoJsonUrl = ''
    dateFrom = ''
    dateTo = ''
    if request.method == "POST":
        daterange = request.form['daterange']
        dates = daterange.split()
        dateFrom = dates[0]
        dateTo = dates[1]
        geoJsonUrl = f"https://data.calgary.ca/resource/c2es-76ed.geojson?$where=issueddate%20%3E%20%27{dateFrom}%27%20and%20issueddate%20%3C%20%27{dateTo}%27";

    print(geoJsonUrl)
    return render_template('index.html', geoJsonUrl=geoJsonUrl, dateFrom=dateFrom, dateTo=dateTo)

@app.route("/search")
def search():
    return render_template('search.html')

