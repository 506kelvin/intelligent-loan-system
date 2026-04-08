from flask import Flask, render_template, session, redirect, url_for, flash, request
from db import get_db_connection
from models.user_model import get_user_by_email, verify_password
from datetime import datetime
from models.user_model import get_all_users
from datetime import datetime
from dateutil.relativedelta import relativedelta

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
    # Ensure this is a dictionary cursor so member['monthly_income'] works
    cursor = conn.cursor(dictionary=True)

    # Fetch members and loan types for the dropdowns
    cursor.execute("SELECT member_number, full_name FROM Members")
    members = cursor.fetchall()
    cursor.execute("SELECT loan_type_id, loan_name, interest_rate, max_repayment_period FROM loantypes")
    loan_types = cursor.fetchall()

    if request.method == 'POST':
        # 1. Collect Form Data
        member_number = request.form['member_number']
        loan_type_id = request.form['loan_type_id']
        loan_amount = float(request.form['loan_amount'])
        repayment_period = int(request.form['repayment_period'])
        loan_purpose = request.form['loan_purpose']
        monthly_installment = loan_amount / repayment_period

        # 2. Fetch required data for the Decision Engine
        from loan_rules import calculate_loan_decision
        
        # Get Member Details
        cursor.execute("SELECT * FROM Members WHERE member_number = %s", (member_number,))
        member = cursor.fetchone()
        
        # --- NEW: Fetch Transaction History ---
        cursor.execute("""
            SELECT amount, balance_after, transaction_type, transaction_date 
            FROM Transactions 
            WHERE member_number = %s 
            ORDER BY transaction_date DESC 
            LIMIT 30
        """, (member_number,))
        transactions = cursor.fetchall()
        # --------------------------------------

        loan_data = {
            "loan_amount": loan_amount,
            "monthly_installment": monthly_installment
        }

        # 3. Run Decision Engine (Now passing 3 arguments)
        score, decision, reasons = calculate_loan_decision(member, loan_data, transactions)

        # 4. Save to Database
        insert_query = """
            INSERT INTO loan_applications (
                member_number, loan_type_id, loan_amount,
                repayment_period, monthly_installment, loan_purpose, status, score, 
                decision_notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(insert_query, (
            member_number, loan_type_id, loan_amount,
            repayment_period, monthly_installment, loan_purpose, 
            decision, score, ", ".join(reasons)
        ))

        conn.commit()
        loan_id = cursor.lastrowid

        cursor.close()
        conn.close()

        return redirect(url_for('add_guarantor', loan_id=loan_id))

    return render_template('apply_loan.html', members=members, loan_types=loan_types)


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

    # Get loan + member details
    cursor.execute("""
        SELECT l.*, m.full_name
        FROM loan_applications l
        JOIN Members m ON l.member_number = m.member_number
        WHERE l.loan_id = %s
    """, (loan_id,))

    loan = cursor.fetchone()

    cursor.close()
    conn.close()

    # Convert notes into list
    reasons = loan['decision_notes'].split(",") if loan['decision_notes'] else []

    return render_template(
        'loan_result.html',
        loan=loan,
        reasons=reasons
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
        loan_id = request.form['loan_id']
        actual_payment = float(request.form['actual_payment'])
        current_payment_date_str = request.form['payment_date']
        current_payment_date = datetime.strptime(current_payment_date_str, '%Y-%m-%d')
        
        # 1. Fetch Loan Details
        cursor.execute("""
            SELECT la.*, lt.interest_rate 
            FROM loan_applications la
            JOIN LoanTypes lt ON la.loan_type_id = lt.loan_type_id
            WHERE la.loan_id = %s
        """, (loan_id,))
        loan = cursor.fetchone()

        if not loan:
            flash("Loan record not found.", "error")
            return redirect(url_for('add_repayment'))

        # 2. Check for missing months (Automatic Default Logic)
        cursor.execute("""
            SELECT remaining_balance, month_number, payment_date, payment_status 
            FROM repayments 
            WHERE loan_id = %s 
            ORDER BY repayment_id DESC LIMIT 1
        """, (loan_id,))
        last_repayment = cursor.fetchone()

        # Initial values if this is the first payment
        running_balance = float(last_repayment['remaining_balance']) if last_repayment else float(loan['loan_amount'])
        next_month_num = (last_repayment['month_number'] + 1) if last_repayment else 1

        current_payment_date_str = request.form['payment_date']
        current_payment_date = datetime.strptime(current_payment_date_str, '%Y-%m-%d').date()
        
        # Determine the date from which to start checking for gaps
        if last_repayment:
            last_date = last_repayment['payment_date']
            if isinstance(last_date, str):
                last_date = datetime.strptime(last_date, '%Y-%m-%d')
            elif hasattr(last_date, 'date'):
                last_date = last_date.date()
        else:
            # Assume first payment is due one month after application
            last_date = current_payment_date - relativedelta(months=1)

        # Loop to fill in gaps if the user skipped months
        temp_date = last_date + relativedelta(months=1)
        while temp_date < current_payment_date:
            raw_rate = float(loan['interest_rate'])
            int_rate_dec = (raw_rate / 100) / 12
            interest_charged = running_balance * int_rate_dec
            penalty = 250.0  # Fixed penalty as per lecturer's table
            
            running_balance = (running_balance + interest_charged + penalty)
            
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

        # 3. Record the Actual Payment (Current Month)
        raw_rate = float(loan['interest_rate'])
        interest_rate_decimal = (raw_rate / 100) / 12
        interest_charged = running_balance * interest_rate_decimal
        
        penalty_charged = 0.0 # No penalty if they are paying today
        
        # New balance calculation
        remaining_balance = (running_balance + interest_charged + penalty_charged) - actual_payment
        
        # Determine Status
        if remaining_balance <= 0:
            status = "Loan Cleared"
        elif last_repayment and last_repayment['payment_status'] == "Defaulted":
            status = "Late Recovery"
        else:
            status = "Paid"

        cursor.execute("""
            INSERT INTO repayments (
                loan_id, month_number, principal_balance, interest_rate,
                interest_charged, expected_payment, actual_payment,
                penalty_charged, remaining_balance, payment_status, payment_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            loan_id, next_month_num, running_balance, raw_rate,
            interest_charged, loan['monthly_installment'], actual_payment,
            penalty_charged, remaining_balance, status, current_payment_date_str
        ))

        conn.commit()
        cursor.close()
        conn.close()

        flash(f"Repayment recorded. Status: {status}", "success")
        return redirect(url_for('loan_statement', loan_id=loan_id))

    # GET: Load loans for dropdown
    cursor.execute("SELECT loan_id, member_number FROM loan_applications WHERE status='Approved'")
    loans = cursor.fetchall()
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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)





