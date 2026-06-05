"""
features/health.py
Health checks and monitoring.
"""

import logging
import os
from datetime import datetime, timezone
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


def check_llm_api() -> dict:
    try:
        from kaplen.features.llm_provider import get_provider
        provider = get_provider()
        provider.complete([{"role": "user", "content": "ok"}], max_tokens=10)
        return {'status': 'healthy', 'message': f'LLM API connected ({provider.model_name})'}
    except Exception as e:
        logger.error(f"LLM API health check failed: {e}")
        return {'status': 'unhealthy', 'message': f'LLM API error: {str(e)}'}


def get_full_health_check() -> dict:
    db_status     = check_database()
    claude_status = check_llm_api()

    if db_status['status'] == 'healthy' and claude_status['status'] == 'healthy':
        overall = 'healthy'
    elif db_status['status'] == 'unhealthy' or claude_status['status'] == 'unhealthy':
        overall = 'unhealthy'
    else:
        overall = 'degraded'

    return {
        'status': overall,
        'timestamp': datetime.now(tz=timezone.utc).isoformat(),
        'version': os.getenv('APP_VERSION', '1.0.0'),
        'components': {
            'database':  db_status,
            'claude_api': claude_status,
        }
    }


def get_quick_health_check() -> dict:
    return {
        'status': 'ok',
        'timestamp': datetime.now(tz=timezone.utc).isoformat(),
        'version': os.getenv('APP_VERSION', '1.0.0'),
    }
