from decimal import Decimal
from collections import defaultdict

# -------------------------
# HELPER FUNCTIONS
# -------------------------

def calculate_adb(transactions):
    """Calculates Average Daily Balance over the provided transaction period."""
    if not transactions:
        return Decimal('0')
    
    total_balance = sum(Decimal(str(t['balance_after'])) for t in transactions)
    days = len(transactions)
    return total_balance / Decimal(str(days))

def detect_deposit_spike(transactions):
    """Checks if the latest deposit is 3x larger than the previous average."""
    deposits = [Decimal(str(t['amount'])) for t in transactions if t['transaction_type'] == 'Deposit']
    
    if len(deposits) < 2:
        return False

    avg_previous_deposit = sum(deposits[:-1]) / (len(deposits) - 1)
    latest_deposit = deposits[-1]

    return latest_deposit > (3 * avg_previous_deposit)

def savings_consistency(transactions):
    """Checks if the member makes at least 2 deposits per month for at least 2 months."""
    monthly_counts = defaultdict(int)

    for t in transactions:
        if t['transaction_type'] == 'Deposit':
            # Assumes transaction_date is a python date/datetime object
            month = t['transaction_date'].strftime("%Y-%m")
            monthly_counts[month] += 1

    consistent_months = sum(1 for m in monthly_counts if monthly_counts[m] >= 2)
    return consistent_months >= 2

# -------------------------
# MAIN CALCULATION ENGINE
# -------------------------

def calculate_loan_decision(member, loan, transactions=None, guarantors=None, collateral=None):
    # Initialize basic variables
    score = 100
    reasons = []
    guarantor_reasons = []
    collateral_reasons = []
    
    income = Decimal(str(member['monthly_income']))
    employment = member['employment_type']
    loan_amount = Decimal(str(loan['loan_amount']))
    repayment = Decimal(str(loan['monthly_installment']))

    # -------------------------
    # 1. ELIGIBILITY RULES
    # -------------------------

    # 1.1 DUPLICATE APPLICATION CHECK
    # This prevents a user from applying if they have a loan already in progress or active
    loan_history = member.get('loan_history', [])
    blocked_statuses = ["Pending", "Active", "Processing"]
    
    if any(prev_loan['status'] in blocked_statuses for prev_loan in loan_history):
        return 0, "Rejected", ["Applicant already has an active or pending loan, so a new loan cannot be issued at this time."], [], []

    # 1.2 MINIMUM INCOME CHECK
    if income < 3000:
        return 0, "Rejected", ["Applicant’s income is below the minimum required level to support loan repayment."], [], []

    # 1.3 EMPLOYMENT RISK
    if employment == "Contract":
        score -= 10
        reasons.append("Applicant has contract-based employment, which may not provide stable long-term income.")
    elif employment == "Self-Employed":
        score -= 15
        reasons.append("Applicant is self-employed, which may result in irregular or unpredictable income.")

    # -------------------------
    # 2. TRANSACTION & SAVINGS RULES
    # -------------------------
    if transactions:
        # 2.1 Average Daily Balance (ADB) Check
        adb = calculate_adb(transactions)
        required_adb = loan_amount * Decimal('0.20') 
        
        if adb < required_adb:
            return 0, "Rejected", [f"Applicant’s account balance is too low compared to the requested loan amount, indicating weak financial capacity. (Required: {required_adb})"], [], []
        else:
            score += 5
            reasons.append("Applicant maintains a healthy account balance, indicating good financial stability.")

        # 2.2 Deposit Spike Detection
        if detect_deposit_spike(transactions):
            score -= 20
            reasons.append("A recent unusually large deposit was detected, which may indicate temporary funds rather than consistent savings.")

        # 2.3 Savings Consistency
        if savings_consistency(transactions):
            score += 10
            reasons.append("Applicant shows consistent saving habits over time, indicating financial discipline.")
        else:
            score -= 5
            reasons.append("Applicant does not maintain consistent savings, which may indicate unstable financial behavior.")

    # -------------------------
    # 3. AFFORDABILITY RULES
    # -------------------------
    dsr = repayment / income
    if dsr > 0.33:
        return 0, "Rejected", ["A large portion of the applicant’s income would be used to repay the loan, making it difficult to manage other expenses."], [], []
    elif dsr > 0.25:
        score -= 15
        reasons.append("A significant portion of the applicant’s income will go toward loan repayment, increasing financial pressure.")

    disposable = income - repayment
    if disposable < 4000:
        return 0, "Rejected", ["After loan repayment, the applicant would not have enough income left to meet basic living expenses."], [], []
    elif disposable < 6000:
        score -= 10
        reasons.append("Applicant has limited income remaining after expenses, which may affect their ability to repay the loan comfortably.")

    # 4. LOAN-TO-INCOME RATIO
    lti = loan_amount / (income * 12)
    if lti > 1:
        score -= 25
        reasons.append("The requested loan amount is too high compared to the applicant’s income.")
    elif lti > 0.5:
        score -= 10
        reasons.append("The loan amount is relatively high compared to income, which may increase repayment risk.")

    # -------------------------
    # 5. GUARANTOR & COLLATERAL
    # -------------------------
    if guarantors:
        total_guaranteed = sum(Decimal(str(g['amount_guaranteed'])) for g in guarantors)
        if total_guaranteed >= loan_amount * Decimal('0.5'):
            score += 10
            guarantor_reasons.append("Guarantors provide sufficient financial backing, reducing the lender’s risk.")
        else:
            score -= 10
            guarantor_reasons.append("Guarantors do not provide enough financial coverage for the requested loan.")
    else:
        score -= 20
        guarantor_reasons.append("No guarantors were provided to support the loan in case of default.")
        
    if collateral:
        total_collateral = sum(Decimal(str(c['certified_value'])) for c in collateral)
        if total_collateral >= loan_amount:
            score += 15
            collateral_reasons.append("The loan is fully secured by collateral, reducing the risk of financial loss.")
        elif total_collateral >= loan_amount * Decimal('0.5'):
            score += 5
            collateral_reasons.append("The loan is partially secured by collateral, offering some protection against default.")
        else:
            score -= 10
            collateral_reasons.append("The value of the collateral is not enough to fully secure the loan.")
    else:
        score -= 10
        collateral_reasons.append("No collateral was provided to secure the loan.")

    # -------------------------
    # FINAL DECISION
    # -------------------------
    if score >= 80:
        decision = "Approved"
    elif score >= 60:
        decision = "Review"
    else:
        decision = "Rejected"

    return score, decision, reasons, guarantor_reasons, collateral_reasons