"""
Authentication and Authorization Module for TravelPlanner.
Handles user registration, password hashing (PBKDF2-HMAC-SHA256),
30-day session token creation/verification, and per-user trip data isolation.
Supports PostgreSQL with an automatic SQLite fallback for serverless/offline deployments.
"""
import os
import sys
import hmac
import time
import secrets
import hashlib
import sqlite3
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

# Ensure paths
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "travelplanner_super_secret_auth_key_2026")
DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_FALLBACK_DIR = Path(__file__).resolve().parent / "data"
SQLITE_FALLBACK_PATH = SQLITE_FALLBACK_DIR / "auth_fallback.db"

# 30-day session lifetime in seconds
SESSION_DURATION_SECONDS = 30 * 24 * 60 * 60

serializer = URLSafeTimedSerializer(AUTH_SECRET_KEY)


def _get_pg_connection():
    """Attempts to create a psycopg connection to PostgreSQL."""
    if not DATABASE_URL:
        return None
    try:
        from psycopg import connect
        conn = connect(DATABASE_URL)
        return conn
    except Exception as e:
        return None


def _get_sqlite_connection():
    """Fallback connection to local SQLite database."""
    SQLITE_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SQLITE_FALLBACK_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db():
    """Initializes the users table in PostgreSQL or SQLite fallback."""
    pg_conn = _get_pg_connection()
    if pg_conn:
        try:
            with pg_conn:
                with pg_conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            id SERIAL PRIMARY KEY,
                            email VARCHAR(255) UNIQUE NOT NULL,
                            password_hash VARCHAR(255) NOT NULL,
                            salt VARCHAR(255) NOT NULL,
                            full_name VARCHAR(255),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
            return "postgresql"
        except Exception:
            pass

    # SQLite fallback
    with _get_sqlite_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    return "sqlite"


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Hashes a password using PBKDF2-HMAC-SHA256 with 200,000 rounds and unique salt."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200000
    ).hex()
    return hashed, salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verifies a password against the stored hash and salt using timing-safe comparison."""
    expected_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(expected_hash, password_hash)


def validate_password_complexity(password: str) -> tuple[bool, Optional[str]]:
    """
    Validates that password meets security requirements:
    1. Minimum length of 8 characters.
    2. At least one uppercase letter (A-Z).
    3. At least one lowercase letter (a-z).
    4. At least one number / digit (0-9).
    5. At least one sign / special character / symbol.
    """
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter (A-Z)."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter (a-z)."
    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number (0-9)."
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Password must contain at least one sign / special character (e.g. !@#$%^&*)."
    return True, None


def register_user(email: str, password: str, full_name: str = "") -> Dict[str, Any]:
    """Registers a new user. Returns user info or error message."""
    email = email.strip().lower()
    full_name = full_name.strip()

    if not email or "@" not in email or "." not in email:
        return {"success": False, "error": "Please provide a valid email address."}
    
    is_valid, err_msg = validate_password_complexity(password)
    if not is_valid:
        return {"success": False, "error": err_msg}

    init_auth_db()
    hashed, salt = hash_password(password)

    # Try PostgreSQL first
    pg_conn = _get_pg_connection()
    if pg_conn:
        try:
            with pg_conn:
                with pg_conn.cursor() as cur:
                    cur.execute("SELECT id FROM users WHERE email = %s;", (email,))
                    if cur.fetchone():
                        return {"success": False, "error": "An account with this email already exists."}
                    cur.execute("""
                        INSERT INTO users (email, password_hash, salt, full_name)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id, email, full_name, created_at;
                    """, (email, hashed, salt, full_name or email.split("@")[0]))
                    row = cur.fetchone()
                    return {
                        "success": True,
                        "user": {
                            "id": row[0],
                            "email": row[1],
                            "full_name": row[2],
                            "created_at": str(row[3])
                        }
                    }
        except Exception as e:
            pass

    # SQLite Fallback
    try:
        with _get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE email = ?;", (email,))
            if cursor.fetchone():
                return {"success": False, "error": "An account with this email already exists."}
            cursor.execute("""
                INSERT INTO users (email, password_hash, salt, full_name)
                VALUES (?, ?, ?, ?);
            """, (email, hashed, salt, full_name or email.split("@")[0]))
            conn.commit()
            user_id = cursor.lastrowid
            return {
                "success": True,
                "user": {
                    "id": user_id,
                    "email": email,
                    "full_name": full_name or email.split("@")[0]
                }
            }
    except Exception as e:
        return {"success": False, "error": f"Registration failed: {str(e)}"}


def authenticate_user(email: str, password: str) -> Dict[str, Any]:
    """Authenticates a user with email and password."""
    email = email.strip().lower()
    if not email or not password:
        return {"success": False, "error": "Email and password are required."}

    init_auth_db()

    # Try PostgreSQL
    pg_conn = _get_pg_connection()
    if pg_conn:
        try:
            with pg_conn:
                with pg_conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, email, password_hash, salt, full_name, created_at
                        FROM users WHERE email = %s;
                    """, (email,))
                    row = cur.fetchone()
                    if not row:
                        return {"success": False, "error": "Invalid email or password."}
                    user_id, db_email, db_hash, db_salt, db_name, db_created = row
                    if verify_password(password, db_hash, db_salt):
                        return {
                            "success": True,
                            "user": {
                                "id": user_id,
                                "email": db_email,
                                "full_name": db_name,
                                "created_at": str(db_created)
                            }
                        }
                    else:
                        return {"success": False, "error": "Invalid email or password."}
        except Exception:
            pass

    # SQLite Fallback
    try:
        with _get_sqlite_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, email, password_hash, salt, full_name, created_at
                FROM users WHERE email = ?;
            """, (email,))
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": "Invalid email or password."}
            if verify_password(password, row["password_hash"], row["salt"]):
                return {
                    "success": True,
                    "user": {
                        "id": row["id"],
                        "email": row["email"],
                        "full_name": row["full_name"],
                        "created_at": str(row["created_at"])
                    }
                }
            return {"success": False, "error": "Invalid email or password."}
    except Exception as e:
        return {"success": False, "error": f"Authentication failed: {str(e)}"}


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves user profile by user ID."""
    pg_conn = _get_pg_connection()
    if pg_conn:
        try:
            with pg_conn:
                with pg_conn.cursor() as cur:
                    cur.execute("SELECT id, email, full_name, created_at FROM users WHERE id = %s;", (user_id,))
                    row = cur.fetchone()
                    if row:
                        return {"id": row[0], "email": row[1], "full_name": row[2], "created_at": str(row[3])}
        except Exception:
            pass

    try:
        with _get_sqlite_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, email, full_name, created_at FROM users WHERE id = ?;", (user_id,))
            row = cur.fetchone()
            if row:
                return {"id": row["id"], "email": row["email"], "full_name": row["full_name"], "created_at": str(row["created_at"])}
    except Exception:
        pass
    return None


def create_session_token(user_id: int, email: str, full_name: str = "") -> str:
    """Creates a cryptographically signed session token with 30 days validity."""
    payload = {
        "user_id": user_id,
        "email": email,
        "full_name": full_name,
        "issued_at": int(time.time())
    }
    return serializer.dumps(payload)


def validate_session_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Validates a session token. Returns payload dict if valid and within 30 days.
    Returns None if expired or tampered.
    """
    if not token or not isinstance(token, str):
        return None
    try:
        payload = serializer.loads(token, max_age=SESSION_DURATION_SECONDS)
        user = get_user_by_id(payload.get("user_id"))
        if user:
            return user
        return payload
    except (SignatureExpired, BadSignature, Exception):
        return None


def format_user_thread_id(user_id: int, base_thread_id: Optional[str] = None) -> str:
    """Formats a thread_id with user isolation prefix: user_{user_id}_{suffix}."""
    if not base_thread_id:
        base_thread_id = f"trip_{secrets.token_hex(4)}"
    # Avoid duplicate prefixes
    if base_thread_id.startswith(f"user_{user_id}_"):
        return base_thread_id
    return f"user_{user_id}_{base_thread_id}"


def get_user_saved_sessions(user_id: int) -> List[str]:
    """
    Queries PostgreSQL checkpoints table for thread_ids belonging ONLY to this user.
    Ensures strict authorization and trip data isolation.
    """
    prefix = f"user_{user_id}_%"
    user_prefix = f"user_{user_id}_"
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return []
    try:
        from psycopg import connect
        with connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id LIKE %s ORDER BY thread_id DESC;",
                    (prefix,)
                )
                rows = cur.fetchall()
                # Return the list of thread_ids for this user
                return [r[0] for r in rows if r[0]]
    except Exception:
        return []
