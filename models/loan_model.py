from db import get_db_connection

def create_loan_application(applicant_name, national_id, phone,
                            amount, income, employment_status):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO loans
        (applicant_name, national_id, phone, amount, income, employment_status)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (applicant_name, national_id, phone,
          amount, income, employment_status))
    

    conn.commit()
    cursor.close()
    conn.close()

def get_all_loans():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM loans ORDER BY created_at DESC")
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
    return []