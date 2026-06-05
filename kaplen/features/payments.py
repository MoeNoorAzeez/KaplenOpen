"""
Payment & Subscription system - MODIFIED FOR YOUR SCHEMA
Wayl integration, billing checks, teacher-level subscriptions

File: features/payments.py
"""

import os
import json
import logging
import hashlib
import hmac
from datetime import datetime, timedelta
from flask import request
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

WAYL_WEBHOOK_SECRET = os.getenv('WAYL_WEBHOOK_SECRET', '')
DEFAULT_PRICE = int(os.getenv('DEFAULT_SUBSCRIPTION_PRICE', '0'))


class WaylError(Exception):
    """Wayl-related errors"""
    pass


def get_db_connection():
    """Get PostgreSQL connection from environment variables."""
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        database=os.getenv('DB_NAME', 'kaplen'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', ''),
        port=int(os.getenv('DB_PORT', '5432'))
    )


def verify_wayl_webhook_signature(body: bytes, signature: str) -> bool:
    """
    Verify webhook signature from Wayl
    """
    expected_signature = hmac.new(
        WAYL_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


def handle_wayl_webhook(data: dict):
    """
    Handle webhook from Wayl payment gateway
    
    Webhook payload:
    {
        'status': 'success' | 'failed',
        'transaction_id': str,
        'teacher_id': str (UUID),
        'amount': int (in fils),
        'currency': 'IQD'
    }
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        status = data.get('status')
        transaction_id = data.get('transaction_id')
        teacher_id = data.get('teacher_id')
        amount = data.get('amount')
        
        logger.info(f"Processing Wayl webhook: {transaction_id} - {status}")
        
        # Check for duplicate transaction
        cur.execute(
            "SELECT id FROM payments WHERE transaction_id = %s",
            (transaction_id,)
        )
        if cur.fetchone():
            logger.warning(f"Duplicate transaction: {transaction_id}")
            conn.close()
            return
        
        # Create payment record
        cur.execute("""
            INSERT INTO payments (teacher_id, amount, currency, status, transaction_id, paid_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            teacher_id,
            amount,
            'IQD',
            status,
            transaction_id,
            datetime.utcnow() if status == 'success' else None
        ))
        
        # Update teacher subscription status
        if status == 'success':
            cur.execute("""
                UPDATE teachers
                SET subscription_status = %s,
                    subscription_expires_at = %s
                WHERE id = %s
            """, ('active', datetime.utcnow() + timedelta(days=30), teacher_id))
            
            logger.info(f"Subscription activated for teacher {teacher_id}")
        
        elif status == 'failed':
            cur.execute("""
                UPDATE teachers
                SET subscription_status = %s
                WHERE id = %s
            """, ('suspended', teacher_id))
            
            logger.warning(f"Subscription suspended for teacher {teacher_id}")
        
        conn.commit()
    
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        conn.rollback()
        raise WaylError(f"Webhook processing failed: {e}")
    finally:
        cur.close()
        conn.close()


def check_subscription_active(teacher_id: str) -> bool:
    """
    Check if teacher has active subscription
    Used before generating scripts
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("""
            SELECT subscription_status, subscription_expires_at 
            FROM teachers 
            WHERE id = %s
        """, (teacher_id,))
        
        result = cur.fetchone()
        
        if not result:
            return False
        
        if result['subscription_status'] != 'active':
            return False
        
        # Check expiry date
        if result['subscription_expires_at']:
            if datetime.utcnow() > result['subscription_expires_at']:
                return False
        
        return True
    
    finally:
        cur.close()
        conn.close()


def require_active_subscription(f):
    """
    Decorator: Require active subscription
    Used on script generation endpoints
    """
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        teacher_id = getattr(request, 'teacher_id', None)
        
        if not teacher_id:
            logger.warning("Script generation blocked: no teacher_id in request")
            return {"error": "Teacher ID not found"}, 400
        
        if not check_subscription_active(teacher_id):
            logger.warning(f"Script generation blocked: no active subscription for {teacher_id}")
            return {"error": "Active subscription required"}, 402
        
        return f(*args, **kwargs)
    
    return decorated_function


def get_billing_status(teacher_id: str) -> dict:
    """
    Get billing status for a teacher
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get teacher info
        cur.execute("""
            SELECT teacher_id, username, subscription_status, subscription_expires_at
            FROM teachers
            WHERE id = %s
        """, (teacher_id,))
        
        teacher = cur.fetchone()
        if not teacher:
            raise WaylError("Teacher not found")
        
        # Get recent payments
        cur.execute("""
            SELECT id, amount, currency, status, transaction_id, paid_at, created_at
            FROM payments
            WHERE id = %s
            ORDER BY created_at DESC
            LIMIT 12
        """, (teacher_id,))
        
        payments = cur.fetchall()
        
        return {
            'teacher_id': teacher_id,
            'username': teacher['username'],
            'subscription_status': teacher['subscription_status'],
            'subscription_expires_at': teacher['subscription_expires_at'].isoformat() if teacher['subscription_expires_at'] else None,
            'monthly_cost_iqd': PRICE_IQD,
            'monthly_cost_display': f"{PRICE_IQD / 1000:.0f} IQD",
            'payment_history': [
                {
                    'id': str(p['id']),
                    'amount': p['amount'],
                    'currency': p['currency'],
                    'status': p['status'],
                    'transaction_id': p['transaction_id'],
                    'paid_at': p['paid_at'].isoformat() if p['paid_at'] else None,
                    'created_at': p['created_at'].isoformat()
                }
                for p in payments
            ]
        }
    
    finally:
        cur.close()
        conn.close()


def get_payment_history(teacher_id: str, limit: int = 50) -> list:
    """
    Get payment history for a teacher
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("""
            SELECT id, amount, currency, status, transaction_id, paid_at, created_at
            FROM payments
            WHERE id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (teacher_id, limit))
        
        payments = cur.fetchall()
        
        return [
            {
                'id': str(p['id']),
                'amount': p['amount'],
                'currency': p['currency'],
                'status': p['status'],
                'transaction_id': p['transaction_id'],
                'paid_at': p['paid_at'].isoformat() if p['paid_at'] else None,
                'created_at': p['created_at'].isoformat()
            }
            for p in payments
        ]
    
    finally:
        cur.close()
        conn.close()
