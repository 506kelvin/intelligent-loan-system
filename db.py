# db.py
import mysql.connector
from mysql.connector import Error
from config import Config

def get_db_connection():
    """
    Establishes and returns a connection to the MySQL database 
    using parameters defined in config.py.
    """
    try:
        connection = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB,
            port=3306  # Standard MySQL port
        )
        
        if connection.is_connected():
            return connection

    except Error as e:
        print(f"Error while connecting to MySQL: {e}")
        return None

# Quick test (Optional)
if __name__ == "__main__":
    conn = get_db_connection()
    if conn:
        print("Successfully connected to loan_ai_system!")
        conn.close()