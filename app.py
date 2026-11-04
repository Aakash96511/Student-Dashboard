
from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "demo-secret-change-before-deployment")

# Demo login accounts
users = {
    "student": {
        "password": "student123",
        "role": "student",
        "name": "Demo Student"
    },
    "teacher": {
        "password": "teacher123",
        "role": "teacher",
        "name": "Demo Teacher"
    }
}


# Login protection
def login_required():
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            if "username" not in session:
                return redirect(url_for("login"))
            return function(*args, **kwargs)
        return wrapper
    return decorator


# Login page
@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = users.get(username)

        if user and user["password"] == password:

            session["username"] = username
            session["role"] = user["role"]
            session["name"] = user["name"]

            return redirect(url_for("dashboard"))

        flash("Invalid username or password")

    return render_template("login.html")


# Student and Teacher Dashboard
@app.route("/dashboard")
@login_required()
def dashboard():

    student = {
        "name": "Aarav Sharma",
        "roll": "DS2026001",
        "course": "B.Tech CSE - Data Science",
        "semester": "4th Semester",
        "cgpa": 8.5,
        "attendance": 92,
        "subjects": 6,
        "assignments": 4
    }

    subjects = [
        {"name": "Database Management", "marks": 85},
        {"name": "Data Structures", "marks": 90},
        {"name": "Operating Systems", "marks": 82},
        {"name": "Computer Networks", "marks": 88},
        {"name": "Design Thinking", "marks": 91},
        {"name": "Product Analytics", "marks": 86}
    ]

    return render_template(
        "dashboard.html",
        name=session["name"],
        role=session["role"],
        student=student,
        subjects=subjects
    )


# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# Start application
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)