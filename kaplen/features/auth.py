"""
features/auth.py
JWT Authentication — login, signup, token validation.
"""

import jwt
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import request
import bcrypt
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

JWT_SECRET = os.getenv('JWT_SECRET', 'dev-jwt-secret-change-in-prod')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_HOURS = 24


class AuthError(Exception):
    """Raised on authentication failures"""
    pass


def hash_password(password: str) -> str:
    """Hash password with bcrypt"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, hash: str) -> bool:
    """Verify password against bcrypt hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hash.encode('utf-8'))


def generate_jwt(user_id: str, teacher_id: str = None, creator_id: str = None, username: str = None, role: str = 'user') -> str:
    """
    Generate JWT token.
    creator_id is the canonical field; teacher_id kept for backward compatibility.
    """
    resolved_creator_id = creator_id or teacher_id
    payload = {
        'user_id': str(user_id),
        'creator_id': str(resolved_creator_id) if resolved_creator_id else None,
        'teacher_id': str(resolved_creator_id) if resolved_creator_id else None,  # backward compat
        'username': username,
        'role': role,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logger.info(f"JWT generated for user {user_id} ({username})")
    return token


def decode_jwt(token: str) -> dict:
    """
    Decode and validate JWT token
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded payload dict
    
    Raises:
        AuthError on invalid/expired token
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        raise AuthError("Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise AuthError("Invalid token")


def extract_token_from_header() -> str:
    """
    Extract JWT from Authorization header
    Expected format: "Bearer <token>"
    """
    auth_header = request.headers.get('Authorization', '')
    
    if not auth_header.startswith('Bearer '):
        raise AuthError("Missing or invalid Authorization header")
    
    token = auth_header[7:]  # Remove "Bearer "
    return token


def require_jwt(f):
    """
    Decorator: Require valid JWT on endpoint.
    Injects user_id, creator_id, teacher_id (alias), username, role into request object.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            token = extract_token_from_header()
            payload = decode_jwt(token)

            request.user_id = payload['user_id']
            request.creator_id = payload.get('creator_id') or payload.get('teacher_id')
            request.teacher_id = request.creator_id  # backward compat alias
            request.username = payload.get('username')
            request.role = payload.get('role', 'user')

            return f(*args, **kwargs)
        
        except AuthError as e:
            logger.warning(f"Auth error: {e}")
            return {"error": str(e)}, 401
        except Exception as e:
            logger.error(f"Unexpected auth error: {e}", exc_info=True)
            return {"error": "Authentication failed"}, 401
    
    return decorated_function


def require_admin(f):
    """
    Decorator: Require user to be admin.
    Must be used AFTER @require_jwt.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        role = getattr(request, 'role', None)
        if role != 'admin':
            logger.warning(f"Access denied: user {request.user_id} is not admin")
            return {"error": "Insufficient permissions"}, 403
        return f(*args, **kwargs)

    return decorated_function


def get_db_connection():
    """Get PostgreSQL connection from environment variables."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME', 'kaplen'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', ''),
            port=int(os.getenv('DB_PORT', '5432'))
        )
        return conn
    except Exception as e:
        logger.error(f"DB connection error: {e}")
        raise AuthError("Database connection failed")


# Auth Endpoints

def signup_user(email: str, password: str, username: str, name: str = None) -> dict:
    """
    Create new user account
    
    Args:
        email: User email (unique)
        password: Plain text password (will be hashed)
        username: Username (for display, matches teacher)
        name: Full name (optional)
    
    Returns:
        {user_id, username, email, token}
    
    Raises:
        AuthError if email already exists
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Check if email exists
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            logger.warning(f"Signup failed: email {email} already exists")
            raise AuthError("Email already registered")
        
        # Check if username exists
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            logger.warning(f"Signup failed: username {username} already exists")
            raise AuthError("Username already taken")
        
        # Hash password
        password_hash = hash_password(password)
        
        # Create user
        cur.execute("""
            INSERT INTO users (email, password_hash, username, name, role, subscription_status)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (email, password_hash, username, name or username, 'user', 'pending'))
        
        user_id = cur.fetchone()['id']
        conn.commit()
        
        logger.info(f"User created: {user_id} ({email})")
        
        # Generate JWT
        token = generate_jwt(user_id, username=username, role='user')
        
        return {
            'user_id': str(user_id),
            'username': username,
            'email': email,
            'token': token
        }
    
    except AuthError:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise AuthError(f"Signup failed: {str(e)}")
    finally:
        cur.close()
        conn.close()


def login_user(email: str, password: str) -> dict:
    """
    Authenticate user with email/password
    
    Args:
        email: User email
        password: Plain text password
    
    Returns:
        {user_id, username, email, token, subscription_status, teacher_id}
    
    Raises:
        AuthError on invalid credentials
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Lookup user AND teacher (LEFT JOIN to get teacher_id if exists)
        cur.execute("""
            SELECT u.id, u.username, u.email, u.password_hash, u.subscription_status, u.role,
                   t.id as teacher_id
            FROM users u
            LEFT JOIN teachers t ON u.id = t.user_id
            WHERE u.email = %s
        """, (email,))
        
        user = cur.fetchone()
        
        if not user:
            logger.warning(f"Login failed: user not found ({email})")
            raise AuthError("Invalid credentials")
        
        # Verify password
        if not verify_password(password, user['password_hash']):
            logger.warning(f"Login failed: password mismatch ({email})")
            raise AuthError("Invalid credentials")
        
        # Check subscription status
        if user['subscription_status'] not in ['active', 'pending']:
            logger.warning(f"Login blocked: subscription {user['subscription_status']} for {email}")
            raise AuthError("Account suspended")
        
        token = generate_jwt(
            user['id'],
            creator_id=user['teacher_id'],
            username=user['username'],
            role=user['role'],
        )

        logger.info(f"User logged in: {user['id']} ({email})")

        return {
            'user_id': str(user['id']),
            'username': user['username'],
            'email': email,
            'token': token,
            'subscription_status': user['subscription_status'],
            'creator_id': str(user['teacher_id']) if user['teacher_id'] else None,
            'teacher_id': str(user['teacher_id']) if user['teacher_id'] else None,  # backward compat
        }
    
    except AuthError:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise AuthError("Login failed")
    finally:
        cur.close()
        conn.close()


def get_current_user(user_id: str) -> dict:
    """
    Get current authenticated user from user_id
    
    Returns:
        User dict from database
    
    Raises:
        AuthError if not found
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("""
            SELECT id, username, email, name, role, subscription_status, created_at 
            FROM users 
            WHERE id = %s
        """, (user_id,))
        
        user = cur.fetchone()
        if not user:
            raise AuthError("User not found")
        
        return user
    
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise AuthError("Could not retrieve user")
    finally:
        cur.close()
        conn.close()
