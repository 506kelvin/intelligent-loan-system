from decimal import Decimal
from collections import defaultdict

# -------------------------
# HELPER FUNCTIONS
# -------------------------

def calculate_adb(transactions):
    """Calculates Average Daily Balance over the provided transaction period."""
    if not transactions:
        return Decimal('0')
    
    # Summing the 'balance_after' field from your transaction history
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

def calculate_loan_decision(member, loan, transactions=None):
    score = 100
    reasons = []

    income = Decimal(str(member['monthly_income']))
    employment = member['employment_type']
    loan_amount = Decimal(str(loan['loan_amount']))
    repayment = Decimal(str(loan['monthly_installment']))

    # 1. ELIGIBILITY RULES
    if income < 3000:
        return 0, "Rejected", ["Income below minimum threshold"]

    if employment == "Contract":
        score -= 10
        reasons.append("Contract employment risk")
    elif employment == "Self-Employed":
        score -= 15
        reasons.append("Self-employment risk")

    # 2. TRANSACTION & SAVINGS RULES (New Features)
    if transactions:
        # 2.1 Average Daily Balance (ADB) Check
        adb = calculate_adb(transactions)
        required_adb = loan_amount * Decimal('0.20') # 20% of loan amount
        
        if adb < required_adb:
            return 0, "Rejected", [f"Low Average Daily Balance (Required: {required_adb})"]
        else:
            score += 5
            reasons.append("Strong average daily balance")

        # 2.2 Deposit Spike Detection
        if detect_deposit_spike(transactions):
            score -= 20
            reasons.append("Suspicious deposit spike detected")

        # 2.3 Savings Consistency
        if savings_consistency(transactions):
            score += 10
            reasons.append("Consistent savings behavior")
        else:
            score -= 5
            reasons.append("Inconsistent monthly savings")

    # 3. AFFORDABILITY RULES
    dsr = repayment / income
    if dsr > 0.35:
        return 0, "Rejected", ["DSR too high (Debt Service Ratio)"]
    elif dsr > 0.25:
        score -= 15
        reasons.append("Moderate DSR")

    disposable = income - repayment
    if disposable < 4000:
        return 0, "Rejected", ["Below minimum living income"]
    elif disposable < 6000:
        score -= 10
        reasons.append("Low disposable income")

    # 4. LOAN-TO-INCOME RATIO
    lti = loan_amount / (income * 12)
    if lti > 1:
        score -= 25
        reasons.append("High loan-to-income ratio")
    elif lti > 0.5:
        score -= 10
        reasons.append("Moderate loan-to-income ratio")

    # FINAL DECISION
    if score >= 80:
        decision = "Approved"
    elif score >= 60:
        decision = "Review"
    else:
        decision = "Rejected"

    return score, decision, reasons
