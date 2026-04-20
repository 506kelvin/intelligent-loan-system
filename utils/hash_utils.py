import hashlib
from db import get_db_connection

def generate_hash(data_string):
    return hashlib.sha256(data_string.encode()).hexdigest()


def create_loan_hash_string(member_number, loan_amount, repayment_period):
    return f"{member_number}|{float(loan_amount):.2f}|{repayment_period}"


def log_action(loan_id, action, performed_by, old_value=None, new_value=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO audit_logs (loan_id, action, performed_by, old_value, new_value)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        loan_id,
        action,
        performed_by,
        str(old_value),
        str(new_value)
    ))

    conn.commit()
    cursor.close()
    conn.close()