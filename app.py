# app.py
from flask import Flask, render_template_string, session, redirect, url_for, request, render_template
from db import get_db_connection
from models.user_model import get_user_by_email, verify_password
# STEP 3: Import Loan Functions
from models.loan_model import create_loan_application, get_all_loans

app = Flask(__name__)
app.secret_key = "your-secret-key-123"

@app.route('/')
def index():
    return f"<h1>System Status</h1><p>Running smoothly.</p><a href='/login'>Go to Login</a>"

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
    
    # Fetch loans to display on the dashboard
    loans = get_all_loans()
    return render_template("dashboard.html", loans=loans)

# --- STEP 3: LOAN APPLICATION ROUTE ---
@app.route('/loan/new', methods=['GET', 'POST'])
def new_loan():
    # 🔐 Protection: Check if user is logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == 'POST':
        # 1️⃣ Read form data from the user
        applicant_name = request.form.get("applicant_name")
        income = request.form.get("income")
        employment_status = request.form.get("employment_status")
        loan_amount = request.form.get("loan_amount")
        loan_term = request.form.get("loan_term")
        credit_score = request.form.get("credit_score")

        # 2️⃣ Call the model function to save to DB
        success = create_loan_application(
            applicant_name, income, employment_status, 
            loan_amount, loan_term, credit_score
        )

        if success:
            return redirect(url_for("dashboard"))
        else:
            return "There was an error submitting your application.", 500

    # If GET, show the form
    return render_template("loan_form.html")

# app.py

@app.route('/loans')
def loan_list():
    # 🔐 Protection: Check if user is logged in
    if "user_id" not in session:
        return redirect(url_for("login"))

    # 1️⃣ Call the model function to get all records
    all_loans = get_all_loans()

    # 2️⃣ Pass the list of loans to the template
    return render_template("loan_list.html", loans=all_loans)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)