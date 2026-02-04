# app.py
from flask import Flask, render_template_string
from db import get_db_connection

app = Flask(__name__)

@app.route('/')
def index():
    # Attempt to connect to the database
    db = get_db_connection()
    
    if db is not None:
        try:
            cursor = db.cursor()
            # Perform a heartbeat query to verify the connection works
            cursor.execute("SELECT 1")
            cursor.fetchone()
            
            status_message = "Database Connected: Loan AI System is running smoothly."
        except Exception as e:
            status_message = f"Database Error: {str(e)}"
        finally:
            cursor.close()
            db.close()
    else:
        status_message = "Connection Failed: Ensure XAMPP/MySQL is running."

    return f"<h1>System Status</h1><p>{status_message}</p>"

if __name__ == '__main__':
    # Set debug=True to see changes without restarting the server
    app.run(debug=True, port=5000)