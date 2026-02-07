# models/loan_model.py
from db import get_db_connection
from mysql.connector import Error

def create_loan_application(applicant_name, income, employment_status, loan_amount, loan_term, credit_score_input):
    """
    Inserts a new loan application into the database.
    Status defaults to 'PENDING' until processed by the AI.
    """
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO loan_applications 
                (applicant_name, income, employment_status, loan_amount, 
                 loan_term, credit_score_input, ml_risk_score, ml_risk_class, approval_status) 
                VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, 'PENDING')
            """
            values = (applicant_name, income, employment_status, loan_amount, loan_term, credit_score_input)
            cursor.execute(query, values)
            conn.commit()
            return True
        except Error as e:
            print(f"Error inserting loan: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    return False

def get_all_loans():
    """Fetches all loan records for the administrative dashboard."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM loan_applications ORDER BY created_at DESC"
            cursor.execute(query)
            return cursor.fetchall()
        except Error as e:
            print(f"Error fetching loans: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    return []