import sqlite3
import hashlib
from datetime import datetime
from typing import List, Tuple, Dict, Any

DB_PATH = "learnsense.db"


def _conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    con = _conn()
    cur = con.cursor()

    # Backward-compatible table (you used this for “history” memory)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        concept TEXT NOT NULL,
        mastery INTEGER NOT NULL,
        note TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    # Attempts per (user, question_hash)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        question_hash TEXT NOT NULL,
        question TEXT NOT NULL,
        student_input TEXT NOT NULL,
        has_image INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)

    # Concept memory dashboard
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_concepts (
        user_id TEXT NOT NULL,
        concept TEXT NOT NULL,
        mastery_est REAL NOT NULL DEFAULT 50.0,
        misconception_count INTEGER NOT NULL DEFAULT 0,
        correct_count INTEGER NOT NULL DEFAULT 0,
        seen_count INTEGER NOT NULL DEFAULT 0,
        last_seen TEXT NOT NULL,
        PRIMARY KEY (user_id, concept)
    )
    """)

    con.commit()
    con.close()


def question_to_hash(question: str) -> str:
    q = (question or "").strip().encode("utf-8")
    return hashlib.sha256(q).hexdigest()[:16]


def record_attempt(user_id: str, question: str, student_input: str, has_image: bool) -> int:
    init_db()
    qh = question_to_hash(question)
    con = _conn()
    cur = con.cursor()

    cur.execute(
        "INSERT INTO attempts (user_id, question_hash, question, student_input, has_image, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, qh, question, student_input, 1 if has_image else 0, datetime.utcnow().isoformat()),
    )
    con.commit()

    cur.execute("SELECT COUNT(*) FROM attempts WHERE user_id=? AND question_hash=?", (user_id, qh))
    attempts_used = int(cur.fetchone()[0])

    con.close()
    return attempts_used


def get_attempts_used(user_id: str, question: str) -> int:
    init_db()
    qh = question_to_hash(question)
    con = _conn()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM attempts WHERE user_id=? AND question_hash=?", (user_id, qh))
    row = cur.fetchone()
    con.close()
    return int(row[0]) if row else 0


def get_user_history(user_id: str) -> List[Tuple[str, int, str, str]]:
    """
    Returns rows like older code expects:
      (concept, mastery%, note, created_at)
    """
    init_db()
    con = _conn()
    cur = con.cursor()
    cur.execute(
        "SELECT concept, mastery, note, created_at FROM history WHERE user_id=? ORDER BY id DESC LIMIT 50",
        (user_id,),
    )
    rows = cur.fetchall()
    con.close()
    return rows


def add_history(user_id: str, concept: str, mastery: int, note: str):
    init_db()
    con = _conn()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO history (user_id, concept, mastery, note, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, concept, int(mastery), note, datetime.utcnow().isoformat()),
    )
    con.commit()
    con.close()


def update_user_concepts(user_id: str, misconceptions: List[Dict[str, Any]], is_correct: bool):
    """
    Heuristic concept memory:
      - seen_count += 1
      - correct_count++ if correct else misconception_count++
      - mastery_est +/- delta, clamped 0..100
    """
    init_db()
    con = _conn()
    cur = con.cursor()

    now = datetime.utcnow().isoformat()
    delta = 4.0 if is_correct else -6.0

    if not misconceptions:
        misconceptions = [{"concept": "General Understanding"}]

    for m in misconceptions:
        concept = (m.get("concept") or "General Understanding").strip()

        cur.execute(
            "SELECT mastery_est, misconception_count, correct_count, seen_count FROM user_concepts WHERE user_id=? AND concept=?",
            (user_id, concept),
        )
        row = cur.fetchone()

        if row:
            mastery_est, mis_cnt, cor_cnt, seen_cnt = row
            seen_cnt += 1
            if is_correct:
                cor_cnt += 1
            else:
                mis_cnt += 1
            mastery_est = max(0.0, min(100.0, float(mastery_est) + delta))
            cur.execute(
                """UPDATE user_concepts
                   SET mastery_est=?, misconception_count=?, correct_count=?, seen_count=?, last_seen=?
                   WHERE user_id=? AND concept=?""",
                (mastery_est, mis_cnt, cor_cnt, seen_cnt, now, user_id, concept),
            )
        else:
            mastery_est = 55.0 if is_correct else 45.0
            mis_cnt = 0 if is_correct else 1
            cor_cnt = 1 if is_correct else 0
            seen_cnt = 1
            cur.execute(
                """INSERT INTO user_concepts
                   (user_id, concept, mastery_est, misconception_count, correct_count, seen_count, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, concept, mastery_est, mis_cnt, cor_cnt, seen_cnt, now),
            )

    con.commit()
    con.close()


def get_concept_dashboard(user_id: str) -> Dict[str, Any]:
    init_db()
    con = _conn()
    cur = con.cursor()

    cur.execute(
        "SELECT concept, mastery_est, misconception_count, seen_count, last_seen FROM user_concepts WHERE user_id=? ORDER BY mastery_est ASC LIMIT 3",
        (user_id,),
    )
    weakest = [
        {
            "concept": r[0],
            "mastery_est": float(r[1]),
            "misconception_count": int(r[2]),
            "seen_count": int(r[3]),
            "last_seen": r[4],
        }
        for r in cur.fetchall()
    ]

    cur.execute(
        "SELECT concept, misconception_count FROM user_concepts WHERE user_id=? ORDER BY misconception_count DESC LIMIT 3",
        (user_id,),
    )
    frequent = [{"concept": r[0], "misconception_count": int(r[1])} for r in cur.fetchall()]

    con.close()
    return {"weakest": weakest, "frequent": frequent}
