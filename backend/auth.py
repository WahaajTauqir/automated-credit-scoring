"""
Authentication module for user login, signup, and JWT token management.
"""

import os
import datetime
from functools import wraps
from flask import request, jsonify, g
import bcrypt
import jwt
from typing import Optional, Dict, Any, Tuple

# JWT Configuration
JWT_SECRET = os.getenv('JWT_SECRET', 'your-super-secret-jwt-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24  # Token expires in 24 hours


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


def generate_token(user_id: int, email: str) -> str:
    """Generate a JWT token for a user."""
    payload = {
        'user_id': user_id,
        'email': email,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_token_from_header() -> Optional[str]:
    """Extract JWT token from Authorization header."""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    return None


def login_required(f):
    """Decorator to require authentication for an endpoint."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_token_from_header()
        
        if not token:
            return jsonify({'error': 'Authentication required', 'code': 'NO_TOKEN'}), 401
        
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token', 'code': 'INVALID_TOKEN'}), 401
        
        # Store user info in Flask's g object for use in the endpoint
        g.user_id = payload.get('user_id')
        g.user_email = payload.get('email')
        
        return f(*args, **kwargs)
    
    return decorated_function


def get_current_user_id() -> Optional[int]:
    """Get the current authenticated user's ID from the request context."""
    return getattr(g, 'user_id', None)


def optional_auth(f):
    """Decorator that extracts user info if token is provided, but doesn't require it."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_token_from_header()
        
        if token:
            payload = decode_token(token)
            if payload:
                g.user_id = payload.get('user_id')
                g.user_email = payload.get('email')
            else:
                g.user_id = None
                g.user_email = None
        else:
            g.user_id = None
            g.user_email = None
        
        return f(*args, **kwargs)
    
    return decorated_function
