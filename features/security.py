import logging
import re
from flask import request

logger = logging.getLogger(__name__)

def apply_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    return response

def setup_security_headers(app):
    @app.after_request
    def add_headers(response):
        return apply_security_headers(response)

def setup_https_redirect(app):
    pass

class SecurityError(Exception):
    pass

def validate_input(data, max_length=10000):
    if len(str(data)) > max_length:
        raise SecurityError("Input exceeds max length")
    return True

def validate_request(data):
    return validate_input(data)

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_password(password):
    return len(password) >= 6

def validate_username(username):
    return len(username) >= 3

def validate_phone(phone):
    return len(phone) >= 7
