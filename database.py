import sqlite3
from pathlib import Path

DB = Path(__file__).with_name('ielts_zone.db')


def connect():
    return sqlite3.connect(DB)


def setup():
    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS students (
            student_id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL, phone TEXT NOT NULL, email TEXT,
            preferred_branch TEXT NOT NULL, has_certificate TEXT NOT NULL,
            status TEXT DEFAULT 'Pending Assessment')''')
        db.execute('''CREATE TABLE IF NOT EXISTS assessments (
            assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER UNIQUE NOT NULL, assessment_method TEXT NOT NULL,
            certificate_type TEXT, certificate_score TEXT, verification_status TEXT,
            test_date TEXT, written_score REAL, speaking_score REAL,
            english_level TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS groups (
            group_id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL, english_level TEXT NOT NULL,
            branch TEXT NOT NULL, schedule TEXT NOT NULL, capacity INTEGER NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS group_assignments (
            student_id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS waiting_list (
            student_id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL,
            waiting_date TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS trial_lessons (
            student_id INTEGER PRIMARY KEY, trial_date TEXT NOT NULL,
            trial_time TEXT NOT NULL, attendance TEXT NOT NULL,
            decision TEXT NOT NULL, notes TEXT)''')
        db.execute("""CREATE TABLE IF NOT EXISTS payments (
            student_id INTEGER PRIMARY KEY,
            amount_due REAL NOT NULL,
            amount_paid REAL NOT NULL,
            payment_method TEXT NOT NULL,
            payment_date TEXT NOT NULL)""")
        # Add missing example groups without deleting existing groups.
        for branch in ('Chilonzor', 'Yunusobod', 'Sergeli'):
            for level in ('A1', 'A2', 'B1', 'B2', 'C1', 'C2'):
                exists = db.execute('''SELECT 1 FROM groups WHERE branch=? AND english_level=?''',
                                    (branch, level)).fetchone()
                if not exists:
                    db.execute('''INSERT INTO groups (group_name, english_level, branch, schedule, capacity)
                                  VALUES (?, ?, ?, ?, ?)''',
                               (f'{level}-{branch[:3].upper()}', level, branch, 'Mon/Wed/Fri 10:00', 10))


def students():
    with connect() as db:
        return db.execute('SELECT * FROM students ORDER BY student_id DESC').fetchall()


def register(name, phone, email, branch, certificate):
    with connect() as db:
        db.execute('''INSERT INTO students (full_name, phone, email, preferred_branch, has_certificate)
                      VALUES (?, ?, ?, ?, ?)''', (name, phone, email, branch, certificate))


def save_assessment(student_id, method, cert_type, cert_score, verification,
                    test_date, written, speaking, level):
    with connect() as db:
        current = db.execute('SELECT status FROM students WHERE student_id=?', (student_id,)).fetchone()
        if not current:
            raise ValueError('Student not found.')
        if current[0] not in ('Pending Assessment', 'Ready for Group Allocation'):
            raise ValueError('This student has already moved beyond assessment.')
        db.execute('''INSERT INTO assessments
            (student_id, assessment_method, certificate_type, certificate_score,
             verification_status, test_date, written_score, speaking_score, english_level)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
             ON CONFLICT(student_id) DO UPDATE SET
             assessment_method=excluded.assessment_method,
             certificate_type=excluded.certificate_type,
             certificate_score=excluded.certificate_score,
             verification_status=excluded.verification_status,
             test_date=excluded.test_date,
             written_score=excluded.written_score,
             speaking_score=excluded.speaking_score,
             english_level=excluded.english_level''',
             (student_id, method, cert_type, cert_score, verification, test_date, written, speaking, level))
        db.execute("UPDATE students SET status='Ready for Group Allocation' WHERE student_id=?", (student_id,))


def assessments():
    with connect() as db:
        return db.execute('''SELECT a.assessment_id,
            COALESCE(s.full_name, 'Student ID: ' || a.student_id),
            a.assessment_method, a.english_level
            FROM assessments a LEFT JOIN students s ON s.student_id=a.student_id
            ORDER BY a.assessment_id DESC''').fetchall()


def eligible_students():
    with connect() as db:
        return db.execute('''SELECT s.student_id, s.full_name, s.preferred_branch, a.english_level
            FROM students s JOIN assessments a ON s.student_id=a.student_id
            WHERE s.status='Ready for Group Allocation'
            AND NOT EXISTS (SELECT 1 FROM group_assignments x WHERE x.student_id=s.student_id)
            AND NOT EXISTS (SELECT 1 FROM waiting_list w WHERE w.student_id=s.student_id)
            ORDER BY s.student_id''').fetchall()


def matching_groups(level, branch):
    with connect() as db:
        return db.execute('''SELECT g.group_id, g.group_name, g.schedule, g.capacity,
            (SELECT COUNT(*) FROM group_assignments x WHERE x.group_id=g.group_id)
            FROM groups g WHERE g.english_level=? AND g.branch=? ORDER BY g.group_name''',
            (level, branch)).fetchall()


def allocate(student_id, group_id, wait_date=None):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        student = db.execute('''SELECT s.status, s.preferred_branch, a.english_level
            FROM students s JOIN assessments a ON a.student_id=s.student_id
            WHERE s.student_id=?''', (student_id,)).fetchone()
        group = db.execute('SELECT english_level, branch, capacity FROM groups WHERE group_id=?',
                           (group_id,)).fetchone()
        if not student or student[0] not in ('Ready for Group Allocation', 'Waiting List'):
            raise ValueError('Student is not eligible for allocation.')
        if not group or (student[2], student[1]) != (group[0], group[1]):
            raise ValueError('Group does not match the student.')
        if db.execute('SELECT 1 FROM group_assignments WHERE student_id=?', (student_id,)).fetchone():
            raise ValueError('Student already has a group.')
        occupied = db.execute('SELECT COUNT(*) FROM group_assignments WHERE group_id=?',
                              (group_id,)).fetchone()[0]
        if occupied < group[2]:
            db.execute('INSERT INTO group_assignments VALUES (?, ?)', (student_id, group_id))
            db.execute('DELETE FROM waiting_list WHERE student_id=?', (student_id,))
            db.execute("UPDATE students SET status='Group Assigned' WHERE student_id=?", (student_id,))
            return 'Student assigned successfully.'
        if wait_date is None:
            raise ValueError('This group is full.')
        if student[0] == 'Waiting List':
            raise ValueError('Student is already on the waiting list.')
        db.execute('INSERT INTO waiting_list VALUES (?, ?, ?)', (student_id, group_id, wait_date))
        db.execute("UPDATE students SET status='Waiting List' WHERE student_id=?", (student_id,))
        return 'Student added to waiting list.'


def waiting_students():
    with connect() as db:
        return db.execute('''SELECT w.student_id, s.full_name, g.group_name, w.waiting_date,
            g.group_id, g.english_level, g.branch
            FROM waiting_list w JOIN students s ON s.student_id=w.student_id
            JOIN groups g ON g.group_id=w.group_id
            ORDER BY w.waiting_date''').fetchall()


def assigned_students():
    with connect() as db:
        return db.execute('''SELECT s.full_name, g.group_name, s.status
            FROM group_assignments x JOIN students s ON s.student_id=x.student_id
            JOIN groups g ON g.group_id=x.group_id''').fetchall()


def trial_candidates():
    with connect() as db:
        return db.execute("""SELECT s.student_id, s.full_name, g.group_name, s.status
            FROM students s JOIN group_assignments ga ON ga.student_id=s.student_id
            JOIN groups g ON g.group_id=ga.group_id
            WHERE s.status IN ('Group Assigned', 'Trial Scheduled', 'Trial Missed')
            ORDER BY s.student_id""").fetchall()


def save_trial(student_id, date, time, attendance, decision, notes):
    if decision == 'Wants to Enroll' and attendance != 'Attended':
        raise ValueError('Student must attend before proceeding to payment.')
    if attendance != 'Attended' and decision == 'Does Not Want to Enroll':
        raise ValueError('Record attendance before a final decision.')
    if attendance == 'Attended' and decision == 'Pending':
        status = 'Trial Completed'
    elif attendance == 'Attended' and decision == 'Wants to Enroll':
        status = 'Ready for Payment'
    elif attendance == 'Attended' and decision == 'Does Not Want to Enroll':
        status = 'Declined'
    elif attendance == 'Not Attended':
        status = 'Trial Missed'
    else:
        status = 'Trial Scheduled'
    with connect() as db:
        current = db.execute('SELECT status FROM students WHERE student_id=?', (student_id,)).fetchone()
        if not current or current[0] not in ('Group Assigned', 'Trial Scheduled', 'Trial Missed'):
            raise ValueError('Student is not eligible for a trial lesson.')
        db.execute("""INSERT INTO trial_lessons
            (student_id, trial_date, trial_time, attendance, decision, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(student_id) DO UPDATE SET
            trial_date=excluded.trial_date, trial_time=excluded.trial_time,
            attendance=excluded.attendance, decision=excluded.decision, notes=excluded.notes""",
            (student_id, date, time, attendance, decision, notes))
        db.execute('UPDATE students SET status=? WHERE student_id=?', (status, student_id))


def trial_records():
    with connect() as db:
        return db.execute("""SELECT s.full_name, t.trial_date, t.trial_time,
            t.attendance, t.decision, s.status
            FROM trial_lessons t JOIN students s ON s.student_id=t.student_id
            ORDER BY t.trial_date DESC""").fetchall()


def payment_candidates():
    with connect() as db:
        return db.execute("""SELECT s.student_id, s.full_name, g.group_name
            FROM students s
            JOIN trial_lessons t ON t.student_id=s.student_id
            JOIN group_assignments ga ON ga.student_id=s.student_id
            JOIN groups g ON g.group_id=ga.group_id
            WHERE s.status='Ready for Payment'
              AND t.attendance='Attended' AND t.decision='Wants to Enroll'
            ORDER BY s.student_id""").fetchall()


def save_payment(student_id, amount_due, amount_paid, method, date):
    if amount_due <= 0 or amount_paid < amount_due:
        raise ValueError('Full payment is required before enrollment.')
    with connect() as db:
        status = db.execute("""SELECT s.status FROM students s
            JOIN trial_lessons t ON t.student_id=s.student_id
            JOIN group_assignments ga ON ga.student_id=s.student_id
            WHERE s.student_id=? AND t.attendance='Attended'
              AND t.decision='Wants to Enroll'""", (student_id,)).fetchone()
        if not status or status[0] != 'Ready for Payment':
            raise ValueError('Student is not ready for payment.')
        db.execute("""INSERT INTO payments
            (student_id, amount_due, amount_paid, payment_method, payment_date)
            VALUES (?, ?, ?, ?, ?)""", (student_id, amount_due, amount_paid, method, date))
        db.execute("UPDATE students SET status='Enrolled' WHERE student_id=?", (student_id,))


def payment_records():
    with connect() as db:
        return db.execute("""SELECT s.full_name, p.amount_due, p.amount_paid,
            p.payment_method, p.payment_date, s.status
            FROM payments p JOIN students s ON s.student_id=p.student_id
            ORDER BY p.payment_date DESC""").fetchall()
