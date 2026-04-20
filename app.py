from flask import Flask, render_template, session, redirect, url_for, flash, request
from db import get_db_connection
from models.user_model import get_user_by_email, verify_password
from datetime import datetime
from models.user_model import get_all_users
from datetime import datetime
from dateutil.relativedelta import relativedelta
from utils.hash_utils import generate_hash


app = Flask(__name__)
app.secret_key = "your-secret-key-123"

import re

# 1. Define the search function
def regex_search(value, pattern):
    if value is None:
        return False
    return bool(re.search(pattern, str(value), re.IGNORECASE))

# 2. Register it as a Jinja2 filter
app.jinja_env.filters['regex_search'] = regex_search

import joblib
model = joblib.load("models/risk_model.pkl")
def predict_loan_status(data):
    prediction = model.predict([data])
    return prediction[0]

@app.context_processor
def inject_global_data():
    return {
        'now': datetime.now(),      
        'version': 'v1.0.4-stable'  
    }

@app.route('/')
def index():
    # This looks for 'templates/index.html'
    return render_template('index.html')

# --- LOGIN ROUTE ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get("email")
        password = request.form.get("password")
        user = get_user_by_email(email)

        if user is None:
            return "Error: User not found!", 401

        if not verify_password(user["password_hash"], password):
            return "Error: Incorrect password!", 401

        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["role"] = user["role"]

        return redirect(url_for("dashboard"))

    return render_template("login.html")

# --- DASHBOARD ---
@app.route('/dashboard')
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch all loans so the worker can pick one
    cursor.execute("SELECT loan_id, member_number, loan_amount FROM loan_applications")
    all_loans = cursor.fetchall()
    
    return render_template("dashboard.html", loans=all_loans)

@app.route('/register-worker', methods=['GET', 'POST'])
def register_worker():
    # Must be logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Must be admin
    if session.get("role") != "admin":
        return "Access denied. Admins only.", 403

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        from models.user_model import create_user
        create_user(name, email, password, "worker")

        return redirect(url_for("dashboard"))

    return render_template("register_worker.html")

@app.route('/apply_loan', methods=['GET', 'POST'])
def apply_loan():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Dropdown data
    cursor.execute("SELECT member_number, full_name FROM Members")
    members = cursor.fetchall()

    cursor.execute("SELECT loan_type_id, loan_name, interest_rate, max_repayment_period FROM loantypes")
    loan_types = cursor.fetchall()

    if request.method == 'POST':
        try:
            # -------------------------------
            # 1. COLLECT FORM DATA
            # -------------------------------
            member_number = request.form['member_number']
            loan_type_id = request.form['loan_type_id']
            loan_amount = float(request.form['loan_amount'])
            repayment_period = int(request.form['repayment_period'])
            loan_purpose = request.form['loan_purpose']

            monthly_installment = loan_amount / repayment_period

            # -------------------------------
            # 2. FETCH MEMBER
            # -------------------------------
            cursor.execute("SELECT * FROM Members WHERE member_number = %s", (member_number,))
            member = cursor.fetchone()

            if not member:
                flash("Member not found", "danger")
                return redirect(url_for('apply_loan'))

            # -------------------------------
            # 3. FETCH TRANSACTIONS
            # -------------------------------
            cursor.execute("""
                SELECT amount, balance_after, transaction_type, transaction_date 
                FROM Transactions 
                WHERE member_number = %s 
                ORDER BY transaction_date DESC 
                LIMIT 30
            """, (member_number,))
            transactions = cursor.fetchall()

            # -------------------------------
            # 4. 🤖 AI PREDICTION
            # -------------------------------
            income = float(member.get('monthly_income', 0))
            loan_term = repayment_period

            # Temporary assumptions (acceptable for your project)
            cibil_score = 600
            self_employed = 1 if member.get("employment_type") == "self-employed" else 0
            education = 1  # assume graduate

            model_input = [
                income,
                loan_amount,
                loan_term,
                cibil_score,
                self_employed,
                education
            ]

            prediction = predict_loan_status(model_input)
            risk_class = "Approved" if prediction == 1 else "Rejected"
            



            # -------------------------------
            # 5. RULE ENGINE
            # -------------------------------
            from loan_rules import calculate_loan_decision

            loan_data = {
                "loan_amount": loan_amount,
                "monthly_installment": monthly_installment
            }
            score, decision, reasons,_, _ = calculate_loan_decision(member, loan_data, transactions)
        

          

            # -------------------------------
            # 6. COMBINE AI + RULES
            # -------------------------------
            if risk_class == "Rejected":
                decision = "Rejected"
                reasons.append("AI model flagged high risk")

            # -------------------------------
            # 7. SAVE TO DATABASE
            # -------------------------------
            insert_query = """
                INSERT INTO loan_applications (
                    member_number, loan_type_id, loan_amount,
                    repayment_period, monthly_installment,
                    loan_purpose, status, score, decision_notes, ml_prediction, record_hash
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            from utils.hash_utils import generate_hash, create_loan_hash_string
            data_string = create_loan_hash_string( member_number, loan_amount, repayment_period)
            record_hash = generate_hash(data_string)
            print("SAVE STRING:", data_string)
            print("SAVE HASH:", record_hash)

            cursor.execute(insert_query, (
                member_number,
                loan_type_id,
                loan_amount,
                repayment_period,
                monthly_installment,
                loan_purpose,
                decision,
                score,
                ", ".join(reasons),
                risk_class, record_hash
            ))

            conn.commit()
            loan_id = cursor.lastrowid
            

            return redirect(url_for('add_guarantor', loan_id=loan_id))

        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
            return redirect(url_for('apply_loan'))

        finally:
            cursor.close()
            conn.close()

    return render_template('apply_loan.html', members=members, loan_types=loan_types)


@app.route('/verify_loan/<int:loan_id>')
def verify_loan(loan_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM loan_applications WHERE loan_id = %s", (loan_id,))
    loan = cursor.fetchone()

    cursor.close()
    conn.close()

    if not loan:
        return "Loan not found"

    # Recreate data string
    data_string = f"{loan['member_number']}{loan['loan_amount']}{loan['repayment_period']}{loan['status']}{loan['score']}"

    from utils.hash_utils import create_loan_hash_string
    data_string = create_loan_hash_string(
    loan['member_number'],
    loan['loan_amount'],
    loan['repayment_period'],
    loan['status'],
    loan['score']
)

    new_hash = generate_hash(data_string)
    print("VERIFY STRING:", data_string)
    print("VERIFY HASH:", new_hash)
    

    if new_hash == loan['record_hash']:
        return "✅ Data Integrity Verified (No tampering)"
    else:
        return "⚠️ Data has been tampered with!"




@app.route('/add_guarantor/<int:loan_id>', methods=['GET', 'POST'])
def add_guarantor(loan_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch members (to choose guarantor)
    cursor.execute("SELECT member_number, full_name, id_number, employer FROM Members")
    members = cursor.fetchall()

    if request.method == 'POST':
        guarantor_member_number = request.form['guarantor_member_number']
        full_name = request.form['full_name']
        id_number = request.form['id_number']
        employer = request.form['employer']
        amount_guaranteed = request.form['amount_guaranteed']
        deposits = request.form['deposits']

        query = """
            INSERT INTO Guarantors (
                loan_id, guarantor_member_number, full_name,
                id_number, employer, amount_guaranteed, deposits
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(query, (
            loan_id, guarantor_member_number, full_name,
            id_number, employer, amount_guaranteed, deposits
        ))

        conn.commit()

        # You can allow multiple guarantors OR move on
        return redirect(url_for('add_collateral', loan_id=loan_id))

    return render_template('add_guarantor.html', members=members, loan_id=loan_id)

@app.route('/add_collateral/<int:loan_id>', methods=['GET', 'POST'])
def add_collateral(loan_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        collateral_type = request.form['collateral_type']
        owner_name = request.form['owner_name']
        document_number = request.form['document_number']
        certified_value = request.form['certified_value']

        query = """
            INSERT INTO Collateral (
                loan_id, collateral_type, owner_name,
                document_number, certified_value
            )
            VALUES (%s, %s, %s, %s, %s)
        """

        cursor.execute(query, (
            loan_id, collateral_type, owner_name,
            document_number, certified_value
        ))

        conn.commit()

        flash("Loan application completed successfully!", "success")
        return redirect(url_for('loan_result', loan_id=loan_id))

    return render_template('add_collateral.html', loan_id=loan_id)

@app.route('/loan_result/<int:loan_id>')
def loan_result(loan_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Fetch loan + member details
    cursor.execute("""
        SELECT l.*, m.*
        FROM loan_applications l
        JOIN Members m ON l.member_number = m.member_number
        WHERE l.loan_id = %s
    """, (loan_id,))
    loan = cursor.fetchone()

    if not loan:
        cursor.close()
        conn.close()
        return "Loan not found", 404

    # 2. Fetch transactions
    cursor.execute("""
        SELECT amount, balance_after, transaction_type, transaction_date
        FROM Transactions
        WHERE member_number = %s
        ORDER BY transaction_date DESC
        LIMIT 30
    """, (loan['member_number'],))
    transactions = cursor.fetchall()

    # 3. Fetch guarantors
    cursor.execute("""
        SELECT amount_guaranteed
        FROM Guarantors
        WHERE loan_id = %s
    """, (loan_id,))
    guarantors = cursor.fetchall()

    # 4. Fetch collateral
    cursor.execute("""
        SELECT certified_value
        FROM Collateral
        WHERE loan_id = %s
    """, (loan_id,))
    collateral = cursor.fetchall()

    # 5. Prepare loan data
    loan_data = {
        "loan_amount": loan['loan_amount'],
        "monthly_installment": loan['monthly_installment']
    }

    # 6. Recalculate decision (IMPORTANT)
    from loan_rules import calculate_loan_decision

    score, decision, reasons, guarantor_reasons, collateral_reasons = calculate_loan_decision(
        loan,
        loan_data,
        transactions,
        guarantors,
        collateral
    )

    # 7. AI EXPLANATIONS (Simple Explainability)
    ai_reasons = []

    income = float(loan['monthly_income'])
    loan_amount = float(loan['loan_amount'])

    if income < 5000:
        ai_reasons.append("The applicant’s income level increases the likelihood of difficulty in repaying the loan.")

    if loan_amount > income * 12:
        ai_reasons.append("The requested loan amount is high compared to the applicant’s income, increasing repayment risk.")

    if loan.get('employment_type') == "Self-Employed":
        ai_reasons.append("Self-employment may result in irregular income, which can affect consistent loan repayment.")

    if not ai_reasons:
        ai_reasons.append("The applicant meets key financial criteria and shows a low risk of default.")

    cursor.close()
    conn.close()

    # 8. Send everything to template
    return render_template(
        'loan_result.html',
        loan=loan,
        reasons=reasons,
        guarantor_reasons=guarantor_reasons,
        collateral_reasons=collateral_reasons,
        ai_reasons=ai_reasons
    )
@app.route('/users')
def view_users():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Access denied. Admins only.", 403

    from models.user_model import get_all_users
    users = get_all_users()

    return render_template("users.html", users=users)


@app.route('/loans')
def view_loans():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Access denied. Admins only.", 403

    from models.loan_model import get_all_loans
    loans = get_all_loans()

    return render_template("loans.html", loans=loans)


@app.route('/add_member', methods=['GET', 'POST'])
def add_member():
    # Ensure only workers/admin can access
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        pf_number = request.form['pf_number']
        full_name = request.form['full_name']
        id_number = request.form['id_number']
        kra_pin = request.form['kra_pin']
        phone_number = request.form['phone_number']
        email = request.form['email']
        address = request.form['address']
        county = request.form['county']
        sub_county = request.form['sub_county']
        employer = request.form['employer']
        employment_type = request.form['employment_type']
        business_name = request.form['business_name']
        monthly_income = request.form['monthly_income']

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            query = """
                INSERT INTO members (
                    pf_number, full_name, id_number, kra_pin, phone_number, email,
                    address, county, sub_county, employer,
                    employment_type, business_name, monthly_income
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            values = (
                pf_number, full_name, id_number, kra_pin, phone_number, email,
                address, county, sub_county, employer,
                employment_type, business_name, monthly_income
            )

            cursor.execute(query, values)
            conn.commit()

            member_number = cursor.lastrowid
            formatted_member_number = f"SACCO{member_number:05d}"
            
            return render_template(
    'member_success.html', 
    member_number=formatted_member_number, 
    name=full_name
)

            

        except Exception as e:
            flash(f"Error: {str(e)}", "danger")

        finally:
            cursor.close()
            conn.close()

    return render_template('add_member.html')



@app.route('/add_repayment', methods=['GET', 'POST'])
def add_repayment():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        user_id = session['user_id'] # Track who is performing the action
        loan_id = request.form['loan_id']
        actual_payment = float(request.form.get('actual_payment', 0))
        current_payment_date_str = request.form['payment_date']
        current_payment_date = datetime.strptime(current_payment_date_str, '%Y-%m-%d').date()
        
        # 1. Fetch Loan Details with Type Safety
        cursor.execute("""
            SELECT la.*, lt.interest_rate, lt.loan_name
            FROM loan_applications la
            JOIN LoanTypes lt ON la.loan_type_id = lt.loan_type_id
            WHERE la.loan_id = %s
        """, (loan_id,))
        loan = cursor.fetchone()

        if not loan:
            flash("Loan record not found.", "error")
            return redirect(url_for('add_repayment'))

        # Store old balance for the Audit Log
        old_balance = loan.get('remaining_balance') or loan['loan_amount']

        # 2. Get Last Repayment State
        cursor.execute("""
            SELECT remaining_balance, month_number, payment_date, payment_status 
            FROM repayments 
            WHERE loan_id = %s 
            ORDER BY repayment_id DESC LIMIT 1
        """, (loan_id,))
        last_repayment = cursor.fetchone()

        running_balance = float(last_repayment['remaining_balance']) if last_repayment else float(loan['loan_amount'])
        next_month_num = (last_repayment['month_number'] + 1) if last_repayment else 1

        # Determine start date for gap-filling
        if last_repayment:
            last_date = last_repayment['payment_date']
            if isinstance(last_date, str):
                last_date = datetime.strptime(last_date, '%Y-%m-%d').date()
            elif hasattr(last_date, 'date'):
                last_date = last_date.date()
        else:
            last_date = current_payment_date - relativedelta(months=1)

        # --- LOOP: FILL GAPS (AUTOMATIC DEFAULTS) ---
        temp_date = last_date + relativedelta(months=1)
        while temp_date < current_payment_date:
            raw_rate = float(loan['interest_rate'])
            interest_charged = running_balance * ((raw_rate / 100) / 12)
            penalty = 250.0 
            
            running_balance += (interest_charged + penalty)
            
            cursor.execute("""
                INSERT INTO repayments (loan_id, month_number, principal_balance, interest_rate,
                interest_charged, expected_payment, actual_payment, penalty_charged,
                remaining_balance, payment_status, payment_date)
                VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, 'Defaulted', %s)
            """, (loan_id, next_month_num, running_balance - interest_charged - penalty, 
                  raw_rate, interest_charged, loan['monthly_installment'], penalty, 
                  running_balance, temp_date.strftime('%Y-%m-%d')))
            
            next_month_num += 1
            temp_date += relativedelta(months=1)

        # --- RECORD ACTUAL PAYMENT ---
        raw_rate = float(loan['interest_rate'])
        interest_charged = running_balance * ((raw_rate / 100) / 12)
        remaining_balance = (running_balance + interest_charged) - actual_payment
        
        # Determine Status
        if remaining_balance <= 0:
            status = "Loan Cleared"
        elif actual_payment < float(loan['monthly_installment']):
            status = "Partial"
        else:
            status = "Paid"

        cursor.execute("""
            INSERT INTO repayments (
                loan_id, month_number, principal_balance, interest_rate,
                interest_charged, expected_payment, actual_payment,
                penalty_charged, remaining_balance, payment_status, payment_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (loan_id, next_month_num, running_balance, raw_rate,
              interest_charged, loan['monthly_installment'], actual_payment,
              0.0, remaining_balance, status, current_payment_date_str))

        # --- 3. AUDIT LOG & HASH INTEGRITY ---
        # Record the action in audit_logs
        cursor.execute("""
            INSERT INTO audit_logs (loan_id, performed_by, action_type, old_value, new_value)
            VALUES (%s, %s, %s, %s, %s)
        """, (loan_id, user_id, "REPAYMENT_RECORDED", 
              f"Bal: {old_balance}", f"Bal: {remaining_balance}"))

        conn.commit()
        cursor.close()
        conn.close()

        flash(f"Repayment recorded. Status: {status}", "success")
        return redirect(url_for('loan_statement', loan_id=loan_id))

    # --- GET LOGIC (None-safe Coalesce) ---
    cursor.execute("""
        SELECT 
            la.loan_id, la.member_number, la.loan_amount,
            IFNULL(lt.loan_name, 'Unknown') AS loan_name,
            COALESCE(
                (SELECT r.remaining_balance FROM repayments r 
                 WHERE r.loan_id = la.loan_id ORDER BY r.repayment_id DESC LIMIT 1),
                la.loan_amount, 0
            ) AS remaining_balance
        FROM loan_applications la
        LEFT JOIN LoanTypes lt ON la.loan_type_id = lt.loan_type_id
        WHERE la.status='Approved'
    """)
    loans = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('add_repayment.html', loans=loans)

@app.route('/loan_statement/<int:loan_id>')
def loan_statement(loan_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Fetch Loan and Member details for the header
    cursor.execute("""
        SELECT la.*, lt.loan_name, lt.interest_rate 
        FROM loan_applications la
        JOIN LoanTypes lt ON la.loan_type_id = lt.loan_type_id
        WHERE la.loan_id = %s
    """, (loan_id,))
    loan = cursor.fetchone()

    if not loan:
        flash("Loan not found", "error")
        return redirect(url_for('dashboard'))

    # 2. Fetch all repayment history for this loan
    cursor.execute("""
        SELECT * FROM repayments 
        WHERE loan_id = %s 
        ORDER BY month_number ASC
    """, (loan_id,))
    repayments = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('loan_statement.html', loan=loan, repayments=repayments)

# In your app.py or routes.py
@app.route('/get_member_balance/<member_number>')
def get_member_balance(member_number):
    try:
        print(f"DEBUG: Request received for member {member_number}")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT balance_after 
            FROM Transactions 
            WHERE member_number = %s 
            ORDER BY transaction_date DESC 
            LIMIT 1
        """, (member_number,))

        result = cursor.fetchone()

        cursor.close()
        conn.close()

        if result:
            return {"balance": float(result["balance_after"])}, 200

        return {"balance": 0}, 200

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {"error": "Internal Server Error"}, 500
    
@app.route('/update_loan_status/<int:loan_id>', methods=['POST'])
def update_loan_status(loan_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    new_status = request.form.get('status')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE loan_applications
        SET status = %s
        WHERE loan_id = %s
    """, (new_status, loan_id))

    conn.commit()
    cursor.close()
    conn.close()

    flash(f"Loan {new_status} successfully!", "success")

    return redirect(url_for('view_loans'))

@app.route('/system_logs')
def system_logs():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Access denied", 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Fetch loans
    cursor.execute("""
        SELECT loan_id, member_number, loan_amount,
               repayment_period, record_hash
        FROM loan_applications
        ORDER BY loan_id DESC
    """)
    loans = cursor.fetchall()

    from utils.hash_utils import create_loan_hash_string, generate_hash

    logs = []
    tampered_count = 0

    for loan in loans:
        data_string = create_loan_hash_string(
            loan['member_number'],
            loan['loan_amount'],
            loan['repayment_period']
        )

        new_hash = generate_hash(data_string)

        is_ok = new_hash == loan['record_hash']

        if not is_ok:
            tampered_count += 1

        logs.append({
            "loan_id": loan['loan_id'],
            "member_number": loan['member_number'],
            "stored_hash": loan['record_hash'],
            "new_hash": new_hash,
            "status": "OK" if is_ok else "TAMPERED"
        })

    
    
    # 2. Fetch audit logs
        cursor.execute("""
    SELECT 
        a.loan_id, 
        a.action_type AS action,  -- Force the DB name to match your HTML 'action'
        a.old_value, 
        a.new_value, 
        a.timestamp, -- Matches {{ log.created_at }} in your HTML
        u.name AS user_name
    FROM audit_logs a
    LEFT JOIN users u ON a.performed_by = u.id
    ORDER BY a.timestamp DESC
    LIMIT 50
""")
        audit_logs = cursor.fetchall()

    # 2. Fetch audit logs
    # cursor.execute("""
    #     SELECT a.*, u.name as user_name
    #     FROM audit_logs a
    #     LEFT JOIN users u ON a.performed_by = u.id
    #     ORDER BY a.timestamp DESC
    #     LIMIT 50
    # """)
    # audit_logs = cursor.fetchall()

    

    cursor.close()
    conn.close()

    return render_template(
        "system_logs.html",
        logs=logs,
        audit_logs=audit_logs,
        tampered_count=tampered_count
    )

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)





