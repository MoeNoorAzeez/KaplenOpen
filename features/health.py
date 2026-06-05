"""
features/health.py
Health checks and monitoring.
"""

import logging
import os
from datetime import datetime
import psycopg2

logger = logging.getLogger(__name__)


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        database=os.getenv('DB_NAME', 'kaplen'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', ''),
        port=int(os.getenv('DB_PORT', '5432'))
    )


def check_database() -> dict:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return {'status': 'healthy', 'message': 'Database connected'}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {'status': 'unhealthy', 'message': f'Database error: {str(e)}'}


def check_claude_api() -> dict:
    try:
        import anthropic

        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            return {'status': 'unhealthy', 'message': 'ANTHROPIC_API_KEY not set'}

        client = anthropic.Anthropic(api_key=api_key)
        model = os.getenv('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')

        client.messages.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": "ok"}]
        )
        return {'status': 'healthy', 'message': 'Claude API connected'}
    except Exception as e:
        logger.error(f"Claude API health check failed: {e}")
        return {'status': 'unhealthy', 'message': f'Claude API error: {str(e)}'}


def get_full_health_check() -> dict:
    db_status     = check_database()
    claude_status = check_claude_api()

    if db_status['status'] == 'healthy' and claude_status['status'] == 'healthy':
        overall = 'healthy'
    elif db_status['status'] == 'unhealthy' or claude_status['status'] == 'unhealthy':
        overall = 'unhealthy'
    else:
        overall = 'degraded'

    return {
        'status': overall,
        'timestamp': datetime.utcnow().isoformat(),
        'version': os.getenv('APP_VERSION', '1.0.0'),
        'components': {
            'database':  db_status,
            'claude_api': claude_status,
        }
    }


def get_quick_health_check() -> dict:
    return {
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'version': os.getenv('APP_VERSION', '1.0.0'),
    }
