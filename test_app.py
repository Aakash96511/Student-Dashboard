import unittest
import os
from werkzeug.security import check_password_hash
import database
from app import app

class EduPulseFullIntegrationTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.test_client()

    def test_01_login_page_renders(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome to EduPulse", response.data)
        self.assertIn(b"Student Demo", response.data)
        self.assertIn(b"Faculty Demo", response.data)

    def test_02_student_login_and_dashboard(self):
        # Login as student
        response = self.client.post('/', data={
            'username': 'student',
            'password': 'student123'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Aarav Sharma", response.data)
        self.assertIn(b"Cumulative GPA", response.data)
        self.assertIn(b"Database Management Systems", response.data)
        self.assertIn(b"Overall Attendance", response.data)

    def test_03_student_customizes_profile(self):
        # Login first
        self.client.post('/', data={'username': 'student', 'password': 'student123'})
        
        # Customize profile
        response = self.client.post('/student/profile', data={
            'full_name': 'Aarav Sharma (Customized)',
            'email': 'aarav.custom@college.edu',
            'phone': '+91 99999 88888',
            'bio': 'Specializing in Generative AI and Large Language Models.',
            'address': 'Tech Campus Residence Hall B',
            'target_cgpa': '9.6',
            'avatar_color': '#059669'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Aarav Sharma (Customized)", response.data)
        self.assertIn(b"Specializing in Generative AI", response.data)

        # Verify in database
        conn = database.get_db()
        st = conn.execute("SELECT * FROM students WHERE roll_no = 'DS2026001'").fetchone()
        self.assertEqual(st['full_name'], 'Aarav Sharma (Customized)')
        self.assertEqual(st['email'], 'aarav.custom@college.edu')
        self.assertEqual(st['target_cgpa'], 9.6)
        self.assertEqual(st['avatar_color'], '#059669')
        conn.close()

    def test_04_student_customizes_subject_note_and_tasks(self):
        self.client.post('/', data={'username': 'student', 'password': 'student123'})
        
        # Get Aarav's first subject
        conn = database.get_db()
        st = conn.execute("SELECT id FROM students WHERE roll_no = 'DS2026001'").fetchone()
        subj = conn.execute("SELECT id FROM subjects WHERE student_id = ? LIMIT 1", (st['id'],)).fetchone()
        conn.close()

        # Update note
        res = self.client.post(f'/student/subject/{subj["id"]}/note', data={
            'notes': 'Targeting 95+ in final practical lab.'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Targeting 95+ in final practical lab.", res.data)

        # Add task
        res_task = self.client.post('/student/task/add', data={
            'title': 'Complete Neural Network PyTorch Assignment',
            'due_date': 'Sunday 6 PM'
        }, follow_redirects=True)
        self.assertEqual(res_task.status_code, 200)
        self.assertIn(b"Complete Neural Network PyTorch Assignment", res_task.data)

        # Toggle task
        conn = database.get_db()
        task = conn.execute("SELECT id FROM assignments WHERE student_id = ? AND title = 'Complete Neural Network PyTorch Assignment'", (st['id'],)).fetchone()
        conn.close()

        res_toggle = self.client.post(f'/student/task/{task["id"]}/toggle', follow_redirects=True)
        self.assertEqual(res_toggle.status_code, 200)

        # Delete task
        res_del = self.client.post(f'/student/task/{task["id"]}/delete', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)

    def test_05_student_changes_password(self):
        self.client.post('/', data={'username': 'student', 'password': 'student123'})
        res = self.client.post('/student/change-password', data={
            'current_password': 'student123',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Password updated successfully", res.data)

        # Logout and re-login with new password
        self.client.get('/logout')
        res_login = self.client.post('/', data={
            'username': 'student',
            'password': 'newpassword123'
        }, follow_redirects=True)
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b"Aarav Sharma", res_login.data)

        # Reset back for subsequent tests
        self.client.post('/student/change-password', data={
            'current_password': 'newpassword123',
            'new_password': 'student123',
            'confirm_password': 'student123'
        })

    def test_06_teacher_login_and_dashboard_metrics(self):
        self.client.get('/logout')
        response = self.client.post('/', data={
            'username': 'teacher',
            'password': 'teacher123'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Faculty Administration Dashboard", response.data)
        self.assertIn(b"Total Enrolled", response.data)
        self.assertIn(b"Class Average CGPA", response.data)
        self.assertIn(b"Student Roster", response.data)

    def test_07_teacher_adds_new_student(self):
        self.client.post('/', data={'username': 'teacher', 'password': 'teacher123'})

        # Clean up if exists from previous run
        conn = database.get_db()
        existing = conn.execute("SELECT user_id FROM students WHERE roll_no = 'DS2026099'").fetchone()
        if existing:
            conn.execute("DELETE FROM users WHERE id = ?", (existing['user_id'],))
            conn.commit()
        conn.close()

        # Add new student
        response = self.client.post('/teacher/students/add', data={
            'full_name': 'Meera Krishnan',
            'username': 'meera',
            'password': 'meera123',
            'roll_no': 'DS2026099',
            'course': 'B.Tech CSE - AI & ML',
            'semester': '4th Semester',
            'batch_year': '2024-2028',
            'email': 'meera.k@college.edu',
            'phone': '+91 91234 56789',
            'target_cgpa': '9.4',
            'remarks': 'Exceptional aptitude in deep learning and math.',
            'include_defaults': 'yes'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Meera Krishnan", response.data)
        self.assertIn(b"DS2026099", response.data)

        # Verify student exists in db with auto-populated subjects
        conn = database.get_db()
        meera = conn.execute("SELECT * FROM students WHERE roll_no = 'DS2026099'").fetchone()
        self.assertIsNotNone(meera)
        subjects = conn.execute("SELECT * FROM subjects WHERE student_id = ?", (meera['id'],)).fetchall()
        self.assertGreater(len(subjects), 0)
        conn.close()

    def test_08_teacher_fills_and_edits_student_data(self):
        self.client.post('/', data={'username': 'teacher', 'password': 'teacher123'})

        conn = database.get_db()
        meera = conn.execute("SELECT * FROM students WHERE roll_no = 'DS2026099'").fetchone()
        meera_id = meera['id']
        conn.close()

        # 1. Teacher adds a custom subject with marks
        res_subj = self.client.post(f'/teacher/student/{meera_id}/add-subject', data={
            'code': 'AIML401',
            'name': 'Deep Reinforcement Learning',
            'credits': '4',
            'marks_obtained': '95',
            'total_marks': '100'
        }, follow_redirects=True)
        self.assertEqual(res_subj.status_code, 200)
        self.assertIn(b"Deep Reinforcement Learning", res_subj.data)
        self.assertIn(b"Grade A+", res_subj.data)

        # 2. Teacher edits an existing subject
        conn = database.get_db()
        subj = conn.execute("SELECT id FROM subjects WHERE student_id = ? AND code = 'AIML401'", (meera_id,)).fetchone()
        conn.close()
        res_edit = self.client.post(f'/teacher/subject/{subj["id"]}/edit', data={
            'student_id': meera_id,
            'code': 'AIML401',
            'name': 'Advanced Deep Reinforcement Learning',
            'credits': '4',
            'marks_obtained': '98',
            'total_marks': '100'
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        self.assertIn(b"Advanced Deep Reinforcement Learning", res_edit.data)

        # 3. Teacher writes advisory remarks
        res_remarks = self.client.post(f'/teacher/student/{meera_id}/edit-profile', data={
            'full_name': 'Meera Krishnan',
            'roll_no': 'DS2026099',
            'course': 'B.Tech CSE - AI & ML',
            'semester': '4th Semester',
            'batch_year': '2024-2028',
            'email': 'meera.k@college.edu',
            'phone': '+91 91234 56789',
            'teacher_remarks': 'Recommended for University AI Honors Fellowship program.'
        }, follow_redirects=True)
        self.assertEqual(res_remarks.status_code, 200)
        self.assertIn(b"Recommended for University AI Honors Fellowship", res_remarks.data)

        # 4. Teacher updates attendance
        conn = database.get_db()
        att = conn.execute("SELECT id FROM attendance WHERE student_id = ? LIMIT 1", (meera_id,)).fetchone()
        conn.close()
        res_att = self.client.post(f'/teacher/student/{meera_id}/edit-attendance', data={
            f'total_classes_{att["id"]}': '45',
            f'attended_classes_{att["id"]}': '43'
        }, follow_redirects=True)
        self.assertEqual(res_att.status_code, 200)
        self.assertIn(b"Attendance records successfully updated", res_att.data)

        # 5. Teacher previews student portal
        res_prev = self.client.get(f'/teacher/student/{meera_id}/preview')
        self.assertEqual(res_prev.status_code, 200)
        self.assertIn(b"Faculty Preview Mode", res_prev.data)
        self.assertIn(b"Meera Krishnan", res_prev.data)

    def test_09_new_student_logs_in_and_sees_teacher_filled_data(self):
        # Meera signs into her portal
        self.client.get('/logout')
        res = self.client.post('/', data={
            'username': 'meera',
            'password': 'meera123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Meera Krishnan", res.data)
        self.assertIn(b"Advanced Deep Reinforcement Learning", res.data)
        self.assertIn(b"Recommended for University AI Honors Fellowship program.", res.data)

    def test_10_teacher_search_and_filter(self):
        self.client.get('/logout')
        self.client.post('/', data={'username': 'teacher', 'password': 'teacher123'})
        
        # Search by name
        res = self.client.get('/dashboard?search=Meera')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Meera Krishnan", res.data)

        # Filter by course (note & is HTML escaped as &amp;)
        res2 = self.client.get('/dashboard?course=B.Tech+CSE+-+AI+%26+ML')
        self.assertEqual(res2.status_code, 200)
        self.assertIn(b"Priya Patel", res2.data)
        self.assertIn(b"B.Tech CSE - AI &amp; ML", res2.data)

    def test_11_teacher_deletes_student(self):
        self.client.get('/logout')
        self.client.post('/', data={'username': 'teacher', 'password': 'teacher123'})

        conn = database.get_db()
        meera = conn.execute("SELECT id, user_id FROM students WHERE roll_no = 'DS2026099'").fetchone()
        conn.close()

        if meera:
            res_del = self.client.post(f'/teacher/student/{meera["id"]}/delete', follow_redirects=True)
            self.assertEqual(res_del.status_code, 200)
            self.assertIn(b"permanently deleted", res_del.data)

            # Verify in DB
            conn = database.get_db()
            deleted_st = conn.execute("SELECT id FROM students WHERE id = ?", (meera["id"],)).fetchone()
            deleted_user = conn.execute("SELECT id FROM users WHERE id = ?", (meera["user_id"],)).fetchone()
            self.assertIsNone(deleted_st)
            self.assertIsNone(deleted_user)
            conn.close()

if __name__ == '__main__':
    unittest.main()
