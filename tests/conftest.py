"""
Pytest configuration for Kaplen smoke tests.

All external services (PostgreSQL, S3, Anthropic) are mocked so the suite
runs without any credentials or live infrastructure.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Set test env vars before any app code is imported.
os.environ.update({
    'FLASK_ENV':             'testing',
    'SECRET_KEY':            'test-secret-key',
    'JWT_SECRET':            'test-jwt-secret',
    'DB_HOST':               'localhost',
    'DB_NAME':               'kaplen_test',
    'DB_USER':               'postgres',
    'DB_PASSWORD':           'test',
    'ANTHROPIC_API_KEY':     'test-key',
    'S3_BUCKET':             'test-bucket',
    'AWS_ACCESS_KEY_ID':     'test-key-id',
    'AWS_SECRET_ACCESS_KEY': 'test-secret',
    'AWS_DEFAULT_REGION':    'us-east-1',
})


def _make_mock_conn():
    mock_conn = MagicMock()
    mock_cur  = MagicMock()
    mock_cur.fetchone.return_value = None
    mock_cur.fetchall.return_value = []
    mock_conn.cursor.return_value  = mock_cur
    return mock_conn, mock_cur


@pytest.fixture(scope='session')
def flask_app():
    """
    Session-scoped Flask app fixture.
    psycopg2.connect is patched for the entire session so DB init does not
    require a live database.
    """
    mock_conn, _ = _make_mock_conn()

    with patch('psycopg2.connect', return_value=mock_conn):
        # Evict any previously imported app modules so env vars take effect.
        for key in [k for k in sys.modules if k.startswith('kaplen')]:
            del sys.modules[key]

        import kaplen.app as kaplen_module
        kaplen_module.app.config['TESTING'] = True
        yield kaplen_module.app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture
def db_mock():
    """
    Function-scoped DB mock for tests that need to control cursor responses.
    Returns (mock_connection, mock_cursor).
    """
    mock_conn, mock_cur = _make_mock_conn()
    with patch('psycopg2.connect', return_value=mock_conn):
        yield mock_conn, mock_cur
