# config.py

class Config:
    # MySQL Database Connection Details
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = ''  # Default for XAMPP is empty
    MYSQL_DB = 'loan_ai_system'

    # Optional: Flask-specific settings if you are using Flask-MySQLDB
    MYSQL_CURSORCLASS = 'DictCursor'