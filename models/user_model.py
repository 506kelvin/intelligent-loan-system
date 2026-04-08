# models/user_model.py
from db import get_db_connection
from mysql.connector import Error
# ✅ STEP 4B: Import the security tools
from werkzeug.security import generate_password_hash, check_password_hash

def get_user_by_email(email):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
    return None

def create_user(name, email, plain_password, role='customer'):
    # ✅ STEP 4C: Convert plain password to secure hash before storing
    hashed_value = generate_password_hash(plain_password)
    
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO users (name, email, password_hash, role) 
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (name, email, hashed_value, role))
            conn.commit()
            return True
        except Error as e:
            print(f"Error: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    return False

# ✅ STEP 4D: Add the verification helper
def verify_password(stored_hash, entered_password):
    """Returns True if password matches, False otherwise."""
    return check_password_hash(stored_hash, entered_password)

def get_all_users():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, name, email, role FROM users")
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
    return []