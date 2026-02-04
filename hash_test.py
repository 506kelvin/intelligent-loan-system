from werkzeug.security import generate_password_hash
# Generate a real hash for 'admin123'
print(generate_password_hash("admin123"))