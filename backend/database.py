
import sqlite3
import os

DATABASE_NAME = os.getenv("DATABASE_PATH", "chat_history.db")


def get_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def create_table():

    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def save_message(session_id, role, content):

    conn = get_connection()

    conn.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content)
    )

    conn.commit()
    conn.close()


def get_history(session_id):

    conn = get_connection()

    messages = conn.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
        (session_id,)
    ).fetchall()

    conn.close()

    return [
        {"role": message["role"], "content": message["content"]}
        for message in messages
    ]
def delete_history(session_id):
    
    conn = get_connection()

    conn.execute(
        "DELETE FROM messages WHERE session_id = ?",
        (session_id,)
    )

    conn.commit()
    conn.close()

def get_all_sessions():
    conn = get_connection()

    sessions = conn.execute("""
        SELECT
            session_id,
            (
                SELECT content
                FROM messages AS m2
                WHERE m2.session_id = messages.session_id
                AND role = 'user'
                ORDER BY id
                LIMIT 1
            ) AS title,
            MAX(created_at) AS updated_at,
            COUNT(*) AS message_count
        FROM messages
        GROUP BY session_id
        ORDER BY MAX(id) DESC
    """).fetchall()

    conn.close()

    return [dict(session) for session in sessions]
