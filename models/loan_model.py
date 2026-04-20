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
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            la.loan_id,
            la.loan_amount,
            la.status,
            la.application_date,

            m.full_name,
            m.phone_number,
            m.monthly_income,
            m.employment_type

        FROM loan_applications la
        JOIN Members m ON la.member_number = m.member_number
        ORDER BY la.loan_id DESC
    """)

    loans = cursor.fetchall()

    cursor.close()
    conn.close()

    return loans