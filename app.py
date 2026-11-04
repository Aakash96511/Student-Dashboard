import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import database

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "edupulse-portal-secure-key-2026")

# Ensure database is initialized on startup
with app.app_context():
    database.init_db()

def get_db_connection():
    if 'db' not in g:
        g.db = database.get_db()
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Role-based access decorator
def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("You do not have permission to view that resource.", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# -------------------------------------------------------------
# AUTHENTICATION
# -------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db_connection()
        user = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]

            if user["role"] == "student":
                student = conn.execute(
                    "SELECT id, full_name, avatar_color FROM students WHERE user_id = ?",
                    (user["id"],)
                ).fetchone()
                if student:
                    session["student_id"] = student["id"]
                    session["name"] = student["full_name"]
                    session["avatar_color"] = student["avatar_color"]
                else:
                    session["name"] = user["username"].capitalize()
                    session["avatar_color"] = "#4f46e5"
            else:
                session["name"] = "Professor " + user["username"].capitalize()
                session["avatar_color"] = "#0284c7"

            flash(f"Welcome back, {session['name']}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password. Please verify and try again.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out safely.", "info")
    return redirect(url_for("login"))


# -------------------------------------------------------------
# MAIN DASHBOARD ROUTE
# -------------------------------------------------------------
@app.route("/dashboard")
@login_required()
def dashboard():
    conn = get_db_connection()
    role = session.get("role")

    if role == "student":
        # Load current student details
        student = conn.execute(
            "SELECT * FROM students WHERE user_id = ?",
            (session["user_id"],)
        ).fetchone()

        if not student:
            flash("Student profile not found. Please contact administration.", "danger")
            return render_template("dashboard.html", student=None, role=role)

        subjects = conn.execute(
            "SELECT * FROM subjects WHERE student_id = ? ORDER BY id ASC",
            (student["id"],)
        ).fetchall()

        attendance = conn.execute(
            "SELECT * FROM attendance WHERE student_id = ? ORDER BY id ASC",
            (student["id"],)
        ).fetchall()

        assignments = conn.execute(
            "SELECT * FROM assignments WHERE student_id = ? ORDER BY id DESC",
            (student["id"],)
        ).fetchall()

        # Compute dynamic CGPA & Attendance
        cgpa = database.calculate_cgpa(subjects)
        overall_attendance = database.calculate_attendance_pct(attendance)
        pending_assignments = sum(1 for a in assignments if a["status"] != "Completed")

        return render_template(
            "student_dashboard.html",
            student=student,
            subjects=subjects,
            attendance=attendance,
            assignments=assignments,
            cgpa=cgpa,
            overall_attendance=overall_attendance,
            pending_assignments=pending_assignments,
            role="student"
        )

    elif role == "teacher":
        search_query = request.args.get("search", "").strip()
        course_filter = request.args.get("course", "").strip()

        # Base query for all students
        query = """
            SELECT s.*, u.username 
            FROM students s
            JOIN users u ON s.user_id = u.id
            WHERE 1=1
        """
        params = []

        if search_query:
            query += " AND (s.full_name LIKE ? OR s.roll_no LIKE ? OR s.email LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        if course_filter:
            query += " AND s.course = ?"
            params.append(course_filter)

        query += " ORDER BY s.id DESC"
        students_raw = conn.execute(query, params).fetchall()

        # Compute metrics for each student and class averages
        student_list = []
        total_cgpa_sum = 0
        total_attendance_sum = 0
        students_with_records = 0

        for s in students_raw:
            subjs = conn.execute("SELECT * FROM subjects WHERE student_id = ?", (s["id"],)).fetchall()
            att = conn.execute("SELECT * FROM attendance WHERE student_id = ?", (s["id"],)).fetchall()
            
            s_cgpa = database.calculate_cgpa(subjs)
            s_att = database.calculate_attendance_pct(att)
            
            student_list.append({
                "data": s,
                "cgpa": s_cgpa,
                "attendance": s_att,
                "subject_count": len(subjs)
            })

            if len(subjs) > 0:
                total_cgpa_sum += s_cgpa
                total_attendance_sum += s_att
                students_with_records += 1

        total_students = len(students_raw)
        avg_cgpa = round(total_cgpa_sum / students_with_records, 2) if students_with_records > 0 else 0.0
        avg_attendance = round(total_attendance_sum / students_with_records, 1) if students_with_records > 0 else 0.0
        honors_count = sum(1 for s in student_list if s["cgpa"] >= 8.5)

        # Get unique course list for filter dropdown
        courses = [row["course"] for row in conn.execute("SELECT DISTINCT course FROM students").fetchall()]

        return render_template(
            "teacher_dashboard.html",
            students=student_list,
            total_students=total_students,
            avg_cgpa=avg_cgpa,
            avg_attendance=avg_attendance,
            honors_count=honors_count,
            courses=courses,
            current_search=search_query,
            current_course=course_filter,
            role="teacher"
        )


# -------------------------------------------------------------
# STUDENT CUSTOMIZATION ROUTES
# -------------------------------------------------------------
@app.route("/student/profile", methods=["GET", "POST"])
@login_required(role="student")
def student_profile():
    conn = get_db_connection()
    student = conn.execute(
        "SELECT * FROM students WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()

    if not student:
        flash("Student record not found.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        bio = request.form.get("bio", "").strip()
        address = request.form.get("address", "").strip()
        avatar_color = request.form.get("avatar_color", "#4f46e5")
        
        try:
            target_cgpa = float(request.form.get("target_cgpa", 9.0))
            target_cgpa = min(10.0, max(0.0, target_cgpa))
        except ValueError:
            target_cgpa = 9.0

        if not full_name:
            flash("Full name cannot be empty.", "danger")
            return redirect(url_for("student_profile"))

        conn.execute("""
            UPDATE students 
            SET full_name = ?, email = ?, phone = ?, bio = ?, address = ?, target_cgpa = ?, avatar_color = ?
            WHERE id = ?
        """, (full_name, email, phone, bio, address, target_cgpa, avatar_color, student["id"]))
        conn.commit()

        session["name"] = full_name
        session["avatar_color"] = avatar_color
        flash("Your profile and custom settings have been saved successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("student_profile.html", student=student)


@app.route("/student/subject/<int:subject_id>/note", methods=["POST"])
@login_required(role="student")
def update_subject_note(subject_id):
    conn = get_db_connection()
    notes = request.form.get("notes", "").strip()

    # Verify subject belongs to this student
    student = conn.execute(
        "SELECT id FROM students WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()

    if student:
        conn.execute(
            "UPDATE subjects SET notes = ? WHERE id = ? AND student_id = ?",
            (notes, subject_id, student["id"])
        )
        conn.commit()
        flash("Personal subject note updated!", "success")
    return redirect(url_for("dashboard"))


@app.route("/student/task/add", methods=["POST"])
@login_required(role="student")
def add_student_task():
    conn = get_db_connection()
    student = conn.execute("SELECT id FROM students WHERE user_id = ?", (session["user_id"],)).fetchone()
    if not student:
        return redirect(url_for("dashboard"))

    title = request.form.get("title", "").strip()
    due_date = request.form.get("due_date", "Upcoming").strip()

    if title:
        conn.execute(
            "INSERT INTO assignments (student_id, title, due_date, status, score) VALUES (?, ?, ?, 'Pending', '-')",
            (student["id"], title, due_date or "Upcoming")
        )
        conn.commit()
        flash("New study task added!", "success")
    return redirect(url_for("dashboard"))


@app.route("/student/task/<int:task_id>/toggle", methods=["POST"])
@login_required(role="student")
def toggle_student_task(task_id):
    conn = get_db_connection()
    student = conn.execute("SELECT id FROM students WHERE user_id = ?", (session["user_id"],)).fetchone()
    if student:
        task = conn.execute("SELECT status FROM assignments WHERE id = ? AND student_id = ?", (task_id, student["id"])).fetchone()
        if task:
            new_status = "Pending" if task["status"] == "Completed" else "Completed"
            conn.execute("UPDATE assignments SET status = ? WHERE id = ?", (new_status, task_id))
            conn.commit()
            flash(f"Task marked as {new_status.lower()}.", "info")
    return redirect(url_for("dashboard"))


@app.route("/student/task/<int:task_id>/delete", methods=["POST"])
@login_required(role="student")
def delete_student_task(task_id):
    conn = get_db_connection()
    student = conn.execute("SELECT id FROM students WHERE user_id = ?", (session["user_id"],)).fetchone()
    if student:
        conn.execute("DELETE FROM assignments WHERE id = ? AND student_id = ?", (task_id, student["id"]))
        conn.commit()
        flash("Task removed.", "info")
    return redirect(url_for("dashboard"))


@app.route("/student/change-password", methods=["POST"])
@login_required(role="student")
def change_password():
    current_pass = request.form.get("current_password", "")
    new_pass = request.form.get("new_password", "")
    confirm_pass = request.form.get("confirm_password", "")

    if not new_pass or len(new_pass) < 6:
        flash("New password must be at least 6 characters long.", "danger")
        return redirect(url_for("student_profile"))

    if new_pass != confirm_pass:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("student_profile"))

    conn = get_db_connection()
    user = conn.execute("SELECT password_hash FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    if not check_password_hash(user["password_hash"], current_pass):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("student_profile"))

    new_hash = generate_password_hash(new_pass)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, session["user_id"]))
    conn.commit()

    flash("Password updated successfully! Please use it on your next login.", "success")
    return redirect(url_for("student_profile"))


# -------------------------------------------------------------
# TEACHER MANAGEMENT ROUTES
# -------------------------------------------------------------
@app.route("/teacher/students/add", methods=["GET", "POST"])
@login_required(role="teacher")
def add_student():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "").strip()
        roll_no = request.form.get("roll_no", "").strip().upper()
        course = request.form.get("course", "").strip()
        semester = request.form.get("semester", "").strip()
        batch_year = request.form.get("batch_year", "2024-2028").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        target_cgpa = float(request.form.get("target_cgpa", 9.0) or 9.0)
        remarks = request.form.get("remarks", "").strip()
        include_defaults = request.form.get("include_defaults") == "yes"

        if not (full_name and username and password and roll_no and course and semester):
            flash("Please fill in all mandatory fields.", "danger")
            return render_template("teacher_add_student.html")

        conn = get_db_connection()
        # Check if username or roll already exists
        existing_user = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing_user:
            flash(f"Username '{username}' is already taken. Please choose another.", "danger")
            return render_template("teacher_add_student.html")

        existing_roll = conn.execute("SELECT id FROM students WHERE roll_no = ?", (roll_no,)).fetchone()
        if existing_roll:
            flash(f"Roll Number '{roll_no}' already exists in records.", "danger")
            return render_template("teacher_add_student.html")

        # 1. Create User
        user_hash = generate_password_hash(password)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'student')",
            (username, user_hash)
        )
        new_user_id = cursor.lastrowid

        # 2. Create Student Record
        cursor.execute("""
            INSERT INTO students (user_id, roll_no, full_name, email, phone, course, semester, batch_year, target_cgpa, teacher_remarks, avatar_color)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (new_user_id, roll_no, full_name, email, phone, course, semester, batch_year, target_cgpa, remarks, "#3b82f6"))
        new_student_id = cursor.lastrowid

        # 3. Optionally attach standard default subjects for this semester
        if include_defaults:
            default_subjects = [
                ("CS301", "Core Subject 1 (Theory)", 4, 80, 100),
                ("CS302", "Core Subject 2 (Theory & Lab)", 4, 85, 100),
                ("CS303", "Applied Elective", 3, 78, 100),
                ("CS304", "Professional Communication", 2, 88, 100)
            ]
            for code, name, creds, marks, total in default_subjects:
                grade, _ = database.calculate_grade(marks, total)
                cursor.execute("""
                    INSERT INTO subjects (student_id, code, name, credits, marks_obtained, total_marks, grade, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, '')
                """, (new_student_id, code, name, creds, marks, total, grade))
                cursor.execute("""
                    INSERT INTO attendance (student_id, subject_name, total_classes, attended_classes)
                    VALUES (?, ?, ?, ?)
                """, (new_student_id, name, 36, 32))

        conn.commit()
        flash(f"Student '{full_name}' ({roll_no}) added successfully! You can now manage their marks and attendance.", "success")
        return redirect(url_for("teacher_student_detail", student_id=new_student_id))

    return render_template("teacher_add_student.html")


@app.route("/teacher/student/<int:student_id>")
@login_required(role="teacher")
def teacher_student_detail(student_id):
    conn = get_db_connection()
    student = conn.execute("""
        SELECT s.*, u.username
        FROM students s
        JOIN users u ON s.user_id = u.id
        WHERE s.id = ?
    """, (student_id,)).fetchone()

    if not student:
        flash("Student record not found.", "danger")
        return redirect(url_for("dashboard"))

    subjects = conn.execute("SELECT * FROM subjects WHERE student_id = ? ORDER BY id ASC", (student_id,)).fetchall()
    attendance = conn.execute("SELECT * FROM attendance WHERE student_id = ? ORDER BY id ASC", (student_id,)).fetchall()
    assignments = conn.execute("SELECT * FROM assignments WHERE student_id = ? ORDER BY id DESC", (student_id,)).fetchall()

    cgpa = database.calculate_cgpa(subjects)
    attendance_pct = database.calculate_attendance_pct(attendance)

    # List all students for quick navigation
    all_students = conn.execute("SELECT id, roll_no, full_name FROM students ORDER BY roll_no ASC").fetchall()

    return render_template(
        "teacher_student_detail.html",
        student=student,
        subjects=subjects,
        attendance=attendance,
        assignments=assignments,
        cgpa=cgpa,
        attendance_pct=attendance_pct,
        all_students=all_students
    )


@app.route("/teacher/student/<int:student_id>/edit-profile", methods=["POST"])
@login_required(role="teacher")
def teacher_edit_student_profile(student_id):
    conn = get_db_connection()
    full_name = request.form.get("full_name", "").strip()
    roll_no = request.form.get("roll_no", "").strip().upper()
    course = request.form.get("course", "").strip()
    semester = request.form.get("semester", "").strip()
    batch_year = request.form.get("batch_year", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    remarks = request.form.get("teacher_remarks", "").strip()

    # Check roll uniqueness if changed
    existing = conn.execute("SELECT id FROM students WHERE roll_no = ? AND id != ?", (roll_no, student_id)).fetchone()
    if existing:
        flash(f"Error: Roll Number '{roll_no}' is already used by another student.", "danger")
        return redirect(url_for("teacher_student_detail", student_id=student_id))

    conn.execute("""
        UPDATE students
        SET full_name = ?, roll_no = ?, course = ?, semester = ?, batch_year = ?, email = ?, phone = ?, teacher_remarks = ?
        WHERE id = ?
    """, (full_name, roll_no, course, semester, batch_year, email, phone, remarks, student_id))
    conn.commit()

    flash("Student information and remarks updated successfully!", "success")
    return redirect(url_for("teacher_student_detail", student_id=student_id))


@app.route("/teacher/student/<int:student_id>/add-subject", methods=["POST"])
@login_required(role="teacher")
def teacher_add_subject(student_id):
    code = request.form.get("code", "").strip().upper()
    name = request.form.get("name", "").strip()
    try:
        credits = int(request.form.get("credits", 3))
        marks = float(request.form.get("marks_obtained", 0))
        total = float(request.form.get("total_marks", 100))
    except ValueError:
        credits, marks, total = 3, 0, 100

    if not name:
        flash("Subject name is required.", "danger")
        return redirect(url_for("teacher_student_detail", student_id=student_id))

    grade, _ = database.calculate_grade(marks, total)

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO subjects (student_id, code, name, credits, marks_obtained, total_marks, grade, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, '')
    """, (student_id, code, name, credits, marks, total, grade))

    # Also automatically add an attendance record for this subject
    conn.execute("""
        INSERT INTO attendance (student_id, subject_name, total_classes, attended_classes)
        VALUES (?, ?, 40, 35)
    """, (student_id, name))

    conn.commit()
    flash(f"Subject '{name}' added with Grade {grade}!", "success")
    return redirect(url_for("teacher_student_detail", student_id=student_id))


@app.route("/teacher/subject/<int:subject_id>/edit", methods=["POST"])
@login_required(role="teacher")
def teacher_edit_subject(subject_id):
    student_id = request.form.get("student_id")
    code = request.form.get("code", "").strip().upper()
    name = request.form.get("name", "").strip()
    try:
        credits = int(request.form.get("credits", 3))
        marks = float(request.form.get("marks_obtained", 0))
        total = float(request.form.get("total_marks", 100))
    except ValueError:
        credits, marks, total = 3, 0, 100

    grade, _ = database.calculate_grade(marks, total)

    conn = get_db_connection()
    conn.execute("""
        UPDATE subjects
        SET code = ?, name = ?, credits = ?, marks_obtained = ?, total_marks = ?, grade = ?
        WHERE id = ?
    """, (code, name, credits, marks, total, grade, subject_id))
    conn.commit()

    flash(f"Subject '{name}' marks updated successfully! (New Grade: {grade})", "success")
    return redirect(url_for("teacher_student_detail", student_id=student_id))


@app.route("/teacher/subject/<int:subject_id>/delete", methods=["POST"])
@login_required(role="teacher")
def teacher_delete_subject(subject_id):
    student_id = request.form.get("student_id")
    conn = get_db_connection()
    conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    conn.commit()
    flash("Subject removed.", "info")
    return redirect(url_for("teacher_student_detail", student_id=student_id))


@app.route("/teacher/student/<int:student_id>/edit-attendance", methods=["POST"])
@login_required(role="teacher")
def teacher_edit_attendance(student_id):
    conn = get_db_connection()
    
    # Check if adding new attendance record
    if request.form.get("action") == "add":
        subject_name = request.form.get("subject_name", "").strip()
        total_classes = int(request.form.get("total_classes", 40))
        attended_classes = int(request.form.get("attended_classes", 30))
        if subject_name:
            conn.execute("""
                INSERT INTO attendance (student_id, subject_name, total_classes, attended_classes)
                VALUES (?, ?, ?, ?)
            """, (student_id, subject_name, total_classes, attended_classes))
            conn.commit()
            flash(f"Attendance record for '{subject_name}' added.", "success")
    else:
        # Batch update existing attendance records
        records = conn.execute("SELECT id FROM attendance WHERE student_id = ?", (student_id,)).fetchall()
        for r in records:
            r_id = r["id"]
            tot_val = request.form.get(f"total_classes_{r_id}")
            att_val = request.form.get(f"attended_classes_{r_id}")
            if tot_val is not None and att_val is not None:
                tot = max(1, int(tot_val))
                att = max(0, min(tot, int(att_val)))
                conn.execute(
                    "UPDATE attendance SET total_classes = ?, attended_classes = ? WHERE id = ?",
                    (tot, att, r_id)
                )
        conn.commit()
        flash("Attendance records successfully updated!", "success")

    return redirect(url_for("teacher_student_detail", student_id=student_id))


@app.route("/teacher/student/<int:student_id>/reset-password", methods=["POST"])
@login_required(role="teacher")
def teacher_reset_password(student_id):
    new_password = request.form.get("new_password", "").strip()
    if not new_password or len(new_password) < 4:
        flash("Password must be at least 4 characters.", "danger")
        return redirect(url_for("teacher_student_detail", student_id=student_id))

    conn = get_db_connection()
    student = conn.execute("SELECT user_id, full_name FROM students WHERE id = ?", (student_id,)).fetchone()
    if student:
        new_hash = generate_password_hash(new_password)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, student["user_id"]))
        conn.commit()
        flash(f"Password for {student['full_name']} has been reset.", "success")

    return redirect(url_for("teacher_student_detail", student_id=student_id))


@app.route("/teacher/student/<int:student_id>/delete", methods=["POST"])
@login_required(role="teacher")
def teacher_delete_student(student_id):
    conn = get_db_connection()
    student = conn.execute("SELECT user_id, full_name, roll_no FROM students WHERE id = ?", (student_id,)).fetchone()
    if student:
        # Delete user which cascades to student, subjects, attendance, assignments
        conn.execute("DELETE FROM users WHERE id = ?", (student["user_id"],))
        conn.commit()
        flash(f"Student record for {student['full_name']} ({student['roll_no']}) has been permanently deleted.", "info")

    return redirect(url_for("dashboard"))


@app.route("/teacher/student/<int:student_id>/preview")
@login_required(role="teacher")
def teacher_preview_student(student_id):
    conn = get_db_connection()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("dashboard"))

    subjects = conn.execute("SELECT * FROM subjects WHERE student_id = ? ORDER BY id ASC", (student_id,)).fetchall()
    attendance = conn.execute("SELECT * FROM attendance WHERE student_id = ? ORDER BY id ASC", (student_id,)).fetchall()
    assignments = conn.execute("SELECT * FROM assignments WHERE student_id = ? ORDER BY id DESC", (student_id,)).fetchall()

    cgpa = database.calculate_cgpa(subjects)
    overall_attendance = database.calculate_attendance_pct(attendance)
    pending_assignments = sum(1 for a in assignments if a["status"] != "Completed")

    return render_template(
        "student_dashboard.html",
        student=student,
        subjects=subjects,
        attendance=attendance,
        assignments=assignments,
        cgpa=cgpa,
        overall_attendance=overall_attendance,
        pending_assignments=pending_assignments,
        role="teacher",
        preview_mode=True
    )


# -------------------------------------------------------------
# APPLICATION ENTRYPOINT
# -------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
