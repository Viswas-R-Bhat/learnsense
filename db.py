import sqlite3

DB_NAME = "learnsense.db"

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS learning_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        concept TEXT,
        mastery INTEGER,
        status TEXT,
        feedback TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

def add_user(user_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (user_id,)
    )
    conn.commit()
    conn.close()

def save_attempt(user_id, concept, mastery, status, feedback):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO learning_attempts
        (user_id, concept, mastery, status, feedback)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, concept, mastery, status, feedback))
    conn.commit()
    conn.close()

def get_user_history(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT concept, mastery, status, timestamp
        FROM learning_attempts
        WHERE user_id = ?
        ORDER BY timestamp DESC
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows
