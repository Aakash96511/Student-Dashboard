import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "student_dashboard.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def calculate_grade(marks, total=100):
    if total <= 0:
        return 'F', 0.0
    pct = (marks / total) * 100
    if pct >= 90:
        return 'A+', 10.0
    elif pct >= 80:
        return 'A', 9.0
    elif pct >= 70:
        return 'B', 8.0
    elif pct >= 60:
        return 'C', 7.0
    elif pct >= 50:
        return 'D', 6.0
    elif pct >= 40:
        return 'E', 5.0
    else:
        return 'F', 0.0

def calculate_cgpa(subjects):
    if not subjects:
        return 0.0
    total_credits = 0
    total_points = 0.0
    for s in subjects:
        credits = s['credits'] if s['credits'] else 3
        marks = s['marks_obtained']
        total = s['total_marks'] if s['total_marks'] else 100
        _, pt = calculate_grade(marks, total)
        total_points += pt * credits
        total_credits += credits
    if total_credits == 0:
        return 0.0
    return round(total_points / total_credits, 2)

def calculate_attendance_pct(attendance_records):
    if not attendance_records:
        return 0.0
    total_classes = sum(r['total_classes'] for r in attendance_records)
    attended = sum(r['attended_classes'] for r in attendance_records)
    if total_classes == 0:
        return 0.0
    return round((attended / total_classes) * 100, 1)

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL, -- 'student' or 'teacher'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        roll_no TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        course TEXT NOT NULL,
        semester TEXT NOT NULL,
        batch_year TEXT DEFAULT '2024-2028',
        bio TEXT DEFAULT '',
        address TEXT DEFAULT '',
        target_cgpa REAL DEFAULT 9.0,
        avatar_color TEXT DEFAULT '#4f46e5',
        teacher_remarks TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        code TEXT,
        name TEXT NOT NULL,
        credits INTEGER DEFAULT 3,
        marks_obtained REAL DEFAULT 0,
        total_marks REAL DEFAULT 100,
        grade TEXT DEFAULT 'A',
        notes TEXT DEFAULT '',
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        subject_name TEXT NOT NULL,
        total_classes INTEGER DEFAULT 40,
        attended_classes INTEGER DEFAULT 36,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        due_date TEXT,
        status TEXT DEFAULT 'Pending', -- 'Pending', 'In Progress', 'Completed'
        score TEXT DEFAULT '-',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    );
    """)

    conn.commit()

    # Seed initial demo accounts if users table is empty
    cursor.execute("SELECT COUNT(*) as count FROM users")
    if cursor.fetchone()['count'] == 0:
        # 1. Create Teacher
        teacher_hash = generate_password_hash("teacher123")
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ("teacher", teacher_hash, "teacher"))

        # 2. Create Default Student: Aarav Sharma
        student_hash = generate_password_hash("student123")
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ("student", student_hash, "student"))
        student_user_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO students (user_id, roll_no, full_name, email, phone, course, semester, batch_year, bio, target_cgpa, avatar_color, teacher_remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            student_user_id,
            "DS2026001",
            "Aarav Sharma",
            "aarav.sharma@college.edu",
            "+91 98765 43210",
            "B.Tech CSE - Data Science",
            "4th Semester",
            "2024-2028",
            "Passionate aspiring machine learning engineer and open source contributor.",
            9.2,
            "#4f46e5",
            "Consistent performer. Keep participating actively in lab projects and assignments."
        ))
        aarav_id = cursor.lastrowid

        # Aarav's subjects
        aarav_subjects = [
            ("CS401", "Database Management Systems", 4, 88, 100, "DBMS lab project completed with high marks."),
            ("CS402", "Data Structures & Algorithms", 4, 92, 100, "Solved 120+ leetcode problems for midterm prep."),
            ("CS403", "Operating Systems", 3, 84, 100, "Need to revise virtual memory paging algorithms."),
            ("CS404", "Computer Networks", 3, 89, 100, "Network topology simulations in Cisco Packet Tracer."),
            ("CS405", "Design Thinking & UI/UX", 2, 91, 100, "Figma design system prototype presented."),
            ("CS406", "Product & Big Data Analytics", 3, 86, 100, "Hands-on dashboard built in Pandas & Streamlit.")
        ]
        for code, name, credits, marks, total, notes in aarav_subjects:
            grade, _ = calculate_grade(marks, total)
            cursor.execute("""
                INSERT INTO subjects (student_id, code, name, credits, marks_obtained, total_marks, grade, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (aarav_id, code, name, credits, marks, total, grade, notes))
            # Also add attendance for each subject
            cursor.execute("""
                INSERT INTO attendance (student_id, subject_name, total_classes, attended_classes)
                VALUES (?, ?, ?, ?)
            """, (aarav_id, name, 42, 39))

        # Aarav's assignments
        aarav_assignments = [
            (aarav_id, "SQL Query Optimization Case Study", "Tomorrow, 11:59 PM", "Pending", "-"),
            (aarav_id, "Graph Traversal & Shortest Path Algorithm", "In 3 Days", "In Progress", "-"),
            (aarav_id, "Process Scheduling Simulation (FCFS / Round Robin)", "Submitted", "Completed", "95/100"),
            (aarav_id, "Figma Interactive Dashboard Prototype", "Submitted", "Completed", "98/100")
        ]
        cursor.executemany("""
            INSERT INTO assignments (student_id, title, due_date, status, score)
            VALUES (?, ?, ?, ?, ?)
        """, aarav_assignments)

        # 3. Create Additional Student: Priya Patel
        priya_hash = generate_password_hash("priya123")
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ("priya", priya_hash, "student"))
        priya_user_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO students (user_id, roll_no, full_name, email, phone, course, semester, batch_year, bio, target_cgpa, avatar_color, teacher_remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            priya_user_id,
            "DS2026002",
            "Priya Patel",
            "priya.patel@college.edu",
            "+91 98123 45678",
            "B.Tech CSE - AI & ML",
            "4th Semester",
            "2024-2028",
            "AI researcher with a keen interest in natural language processing and computer vision.",
            9.5,
            "#059669",
            "Top of the batch in AI algorithms! Outstanding analytical problem solving."
        ))
        priya_id = cursor.lastrowid

        priya_subjects = [
            ("CS401", "Database Management Systems", 4, 94, 100, "Working on distributed database indexing."),
            ("CS402", "Data Structures & Algorithms", 4, 96, 100, "Review dynamic programming state machine techniques."),
            ("CS403", "Operating Systems", 3, 90, 100, "Kernel modules exploration."),
            ("CS404", "Computer Networks", 3, 93, 100, "Socket programming socket.io tutorial.")
        ]
        for code, name, credits, marks, total, notes in priya_subjects:
            grade, _ = calculate_grade(marks, total)
            cursor.execute("""
                INSERT INTO subjects (student_id, code, name, credits, marks_obtained, total_marks, grade, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (priya_id, code, name, credits, marks, total, grade, notes))
            cursor.execute("""
                INSERT INTO attendance (student_id, subject_name, total_classes, attended_classes)
                VALUES (?, ?, ?, ?)
            """, (priya_id, name, 40, 38))

        cursor.execute("""
            INSERT INTO assignments (student_id, title, due_date, status, score)
            VALUES (?, ?, ?, ?, ?)
        """, (priya_id, "Transformer Attention Mechanism Presentation", "In 5 Days", "In Progress", "-"))

        # 4. Create Additional Student: Rohan Verma
        rohan_hash = generate_password_hash("rohan123")
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ("rohan", rohan_hash, "student"))
        rohan_user_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO students (user_id, roll_no, full_name, email, phone, course, semester, batch_year, bio, target_cgpa, avatar_color, teacher_remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rohan_user_id,
            "DS2026003",
            "Rohan Verma",
            "rohan.verma@college.edu",
            "+91 97654 32109",
            "B.Tech CSE - Data Science",
            "4th Semester",
            "2024-2028",
            "Cybersecurity enthusiast and competitive programmer.",
            8.5,
            "#d97706",
            "Good potential. Needs improvement in attendance and regular assignment submissions."
        ))
        rohan_id = cursor.lastrowid

        rohan_subjects = [
            ("CS401", "Database Management Systems", 4, 76, 100, "Review normalization 3NF and BCNF."),
            ("CS402", "Data Structures & Algorithms", 4, 82, 100, "Practice binary tree recursions."),
            ("CS403", "Operating Systems", 3, 71, 100, "Study semaphore deadlocks."),
            ("CS404", "Computer Networks", 3, 75, 100, "TCP/IP handshake flow charts.")
        ]
        for code, name, credits, marks, total, notes in rohan_subjects:
            grade, _ = calculate_grade(marks, total)
            cursor.execute("""
                INSERT INTO subjects (student_id, code, name, credits, marks_obtained, total_marks, grade, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (rohan_id, code, name, credits, marks, total, grade, notes))
            cursor.execute("""
                INSERT INTO attendance (student_id, subject_name, total_classes, attended_classes)
                VALUES (?, ?, ?, ?)
            """, (rohan_id, name, 40, 31))

        conn.commit()

    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
