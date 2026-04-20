import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix
import joblib
import os

# 1. Setup
if not os.path.exists("models"):
    os.makedirs("models")

df = pd.read_csv("dataset/loan_data.csv")

# 2. Force clean column names
df.columns = df.columns.str.strip()

# 3. Robust Data Cleaning
# This handles spaces, case sensitivity, and hidden characters
for col in ["loan_status", "education", "self_employed"]:
    df[col] = df[col].astype(str).str.strip().str.title()

# 4. Explicit Mapping
# We map exactly what we cleaned (Title Case)
df["loan_status"] = df["loan_status"].map({"Approved": 1, "Rejected": 0})
df["education"] = df["education"].map({"Graduate": 1, "Not Graduate": 0})
df["self_employed"] = df["self_employed"].map({"Yes": 1, "No": 0})

# 5. Check for failures
nan_count = df[["loan_status", "education", "self_employed"]].isnull().sum().sum()
if nan_count > 0:
    print(f"Warning: {nan_count} rows could not be mapped. Cleaning them now...")
    df = df.dropna(subset=["loan_status", "education", "self_employed"])

print(f"Final dataset size for training: {len(df)} rows")

# 6. Features and Target
features = [
    "income_annum",
    "loan_amount",
    "loan_term",
    "cibil_score",
    "self_employed",
    "education"
]

X = df[features]
y = df["loan_status"]

# 7. Split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# 8. Train
# Using LogisticRegression - note that CIBIL and Income have high variance,
# so max_iter=1000 helps the model converge.
model = LogisticRegression(max_iter=1000)
model.fit(X_train, y_train)

# 9. Results
y_pred = model.predict(X_test)
print("-" * 30)
print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
print("Confusion Matrix:\n", confusion_matrix(y_test, y_pred))
print("-" * 30)

# 10. Save
joblib.dump(model, "models/risk_model.pkl")
print("Model saved to models/risk_model.pkl")