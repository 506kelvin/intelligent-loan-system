# config.py

class Config:
    # MySQL Database Connection Details
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = ''  # Default for XAMPP is empty
    MYSQL_DB = 'loan_ai_system'

   
    MYSQL_CURSORCLASS = 'DictCursor'