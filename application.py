import os
import requests

from flask import Flask, abort, session, json, render_template, request, flash, redirect, url_for
from flask_session import Session
from sqlalchemy import create_engine, text

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))


@app.route("/")
def index():
    if session.get('username'):
        flash('Hi ' + session.get('username') + '! You can now search for books based on the: title, ISBN, or name of the author.')
    else:
        flash('Please login to search for books!')
    return render_template('index.html')

@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        with engine.connect() as connection:
            qry = text("select * from users where username=:u and password=:p ")
            users = connection.execute(qry, {"u": username, "p": password})
        if users.first():
            session["username"] = username
            return redirect(url_for('index'))
        else:
            flash('Username or Password is incorrect!')
    return render_template('login.html')

@app.route("/logout")
def logout():
    session["username"] = None
    return redirect(url_for('index'))

@app.route("/register", methods=('GET', 'POST'))
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if not username or not password:
            flash('Username and Password are required!')
        else:
            with engine.connect() as connection:
                qry = text("select * from users where username=:u")
                users = connection.execute(qry, {"u": username})
            if users.first():
                flash('That username already exists! Please choose another username.')
            else:
                with engine.connect() as connection:
                    qry = text("insert into users(username,password) values (:u, :p)")
                    connection.execute(qry, {"u": username, "p": password})
                    connection.commit()
                    connection.close()
                return redirect(url_for('index'))
        
    return render_template('register.html')

@app.route("/search")
def search():
    if not session.get('username'):
        return redirect(url_for('index'))

    qry = "select * from books"
    has_where = False
    if 'isbn' in request.args and request.args['isbn'] != '':
        qry = qry + " where isbn like '%" + request.args['isbn'] + "%'"
        has_where = True

    if 'title' in request.args and request.args['title'] != '':
        if has_where: 
            qry = qry + " and"
        else:
            qry = qry + " where"
        qry = qry + " title like '%" + request.args['title'] + "%'"
        has_where = True

    if 'author' in request.args and request.args['author'] != '':
        if has_where: 
            qry = qry + " and"
        else:
            qry = qry + " where"
        qry = qry + " author like '%" + request.args['author'] + "%'"
        has_where = True

    if not has_where:
        return render_template('search.html', books=[])

    with engine.connect() as connection:
        books = connection.execute(text(qry)).all()
    
    if not books:
        flash('No matching books found!')

    return render_template('search.html', books=books)


# Getting book infomation from google books api
def get_google_books_info(isbn):
    response = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}")
    if response.status_code == 200:
        data = response.json()
        if "items" in data:
            book = data["items"][0]
            return book["volumeInfo"]
    print("Google Books API Error: ")
    return None

# Ask Gemini to summarize description
def gemini_summarize_description(description):
    data = {
        "contents": [{
            "parts": [{
                "text": "summarize this text using less than 50 words: " + description
            }]
        }]
    }
    json_data = json.dumps(data)

    apikey = os.environ['GEMINI_API_KEY']
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={apikey}"
    response = requests.post(url, data=json_data, headers={"Content-Type": "application/json"})
    result = response.json()

    if "candidates" in result:
        summary = result["candidates"][0]["content"]["parts"][0]["text"]
    else:
        print("ERROR: No Gemini result!")
        summary = description
        
    return summary


@app.route("/api/<string:isbn>")
def api(isbn):
    if not session.get('username'):
        return redirect(url_for('index'))
    
    with engine.connect() as connection:
        qry = text("select * from books where isbn=:isbn")
        books = connection.execute(qry, {"isbn": isbn})
    
    book = books.first()
    if book:
        book = book._asdict()
    else:
        abort(404)

    description = None
    publishedDate = None
    ratingsCount = None
    averageRating = None
    isbn10 = None
    isbn13 = None
    summarizedDescription = None
    industryIdentifiers = None

    bookinfo = get_google_books_info(isbn)
    if bookinfo:
        description = bookinfo.get("description", None)
        publishedDate = bookinfo.get("publishedDate", None)
        ratingsCount = bookinfo.get("ratingsCount", None)
        averageRating = bookinfo.get("averageRating", None)
        industryIdentifiers = bookinfo.get("industryIdentifiers")
    if industryIdentifiers:
        for x in industryIdentifiers:
            if x["type"] == "ISBN_13":
                isbn13 = x["identifier"]
            elif x["type"] == "ISBN_10":
                isbn10 = x["identifier"]
    if description:
        summarizedDescription = gemini_summarize_description(description)

    data = {
        "title": book["title"],
        "author": book["author"],
        "publishedDate": publishedDate,
        "ISBN_10": isbn10,
        "ISBN_13": isbn13,
        "reviewCount": ratingsCount,
        "averageRating": averageRating,
        "summarizedDescription": summarizedDescription,
        "description": description,
    }
    return data

@app.route("/book/<string:isbn>")
def book(isbn):
    if not session.get('username'):
        return redirect(url_for('index'))
    
    with engine.connect() as connection:
        qry = text("select * from books where isbn=:isbn")
        books = connection.execute(qry, {"isbn": isbn})
        qry = text("select * from reviews where isbn=:isbn")
        reviews = connection.execute(qry, {"isbn": isbn})
    book=books.first()

    bookinfo = get_google_books_info(isbn)
    if bookinfo:
        description = bookinfo.get("description")
        ratingsCount = bookinfo.get("ratingsCount")
        averageRating = bookinfo.get("averageRating")
        summary = gemini_summarize_description(description)
    else:
        description = None
        ratingsCount = None
        averageRating = None
        summary = None

    return render_template('book.html', 
                           book=book,
                           description=description, 
                           ratingsCount=ratingsCount, 
                           averageRating=averageRating,
                           summary=summary, 
                           reviews=reviews)

@app.route("/review", methods=["POST"])
def review():
    username = session.get('username')
    if not username:
        return redirect(url_for('index'))
    
    isbn = request.form['isbn']
    rating = request.form['rating']
    comment = request.form['comment']
    if not comment:
        flash('Please input your comment!')
    else:
        with engine.connect() as connection:
            qry = text(f"select * from reviews where username='{username}' and isbn='{isbn}'")
            reviews = connection.execute(qry)
        if reviews.first():
            flash('You have already left a review about this book!')
        else:
            with engine.connect() as connection:
                qry = text("insert into reviews(isbn,username,comment,rating) values (:isbn, :username, :comment, :rating)")
                connection.execute(qry, {"isbn": isbn, "username": username, "comment": comment, "rating": rating})
                connection.commit()
                connection.close()
    return redirect(url_for('book', isbn=isbn))