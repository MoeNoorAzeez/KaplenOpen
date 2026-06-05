"""
config.py — Centralized configuration
All values from environment variables. No hardcoded secrets.
"""

import os


class Config:
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL')
    DB_HOST = os.getenv('DB_HOST')
    DB_NAME = os.getenv('DB_NAME', 'kaplen')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_PORT = int(os.getenv('DB_PORT', '5432'))

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-change-in-prod')
    JWT_SECRET = os.getenv('JWT_SECRET', 'dev-jwt-secret-change-in-prod')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')

    # AWS
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    S3_BUCKET = os.getenv('S3_BUCKET')

    # LLM provider (provider-agnostic)
    LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'anthropic')   # anthropic | openai
    LLM_API_KEY  = os.getenv('LLM_API_KEY')                 # falls back to provider-specific key
    LLM_MODEL    = os.getenv('LLM_MODEL')                   # falls back to provider default
    LLM_BASE_URL = os.getenv('LLM_BASE_URL')                # for OpenAI-compatible endpoints

    # Provider-specific keys (used as fallbacks by llm_provider.get_provider())
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    ANTHROPIC_MODEL   = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6')
    OPENAI_API_KEY    = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL      = os.getenv('OPENAI_MODEL', 'gpt-4o')

    # Application
    DOMAIN = os.getenv('DOMAIN', 'localhost:5000')
    TIMEZONE = os.getenv('TIMEZONE', 'UTC')
    FRONTEND_PATH = os.getenv('FRONTEND_PATH', './static')

    # Curriculum
    CURRICULUM_REGISTRY_PATH = os.getenv('CURRICULUM_REGISTRY_PATH', 'curricula/registry.json')
    DEFAULT_CURRICULUM_ID = os.getenv('DEFAULT_CURRICULUM_ID', 'iraqi-moe-2024')

    # Payments (optional integrations)
    WAYL_MERCHANT_TOKEN = os.getenv('WAYL_MERCHANT_TOKEN')
    WAYL_WEBHOOK_SECRET = os.getenv('WAYL_WEBHOOK_SECRET')
    WAYL_WEBHOOK_URL = os.getenv('WAYL_WEBHOOK_URL')
    STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')

    # YouTube OAuth (optional)
    YOUTUBE_CLIENT_ID = os.getenv('YOUTUBE_CLIENT_ID')
    YOUTUBE_CLIENT_SECRET = os.getenv('YOUTUBE_CLIENT_SECRET')
    YOUTUBE_OAUTH_REDIRECT_URI = os.getenv('YOUTUBE_OAUTH_REDIRECT_URI')


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    DEBUG = True
    TESTING = True


def get_config():
    env = os.getenv('FLASK_ENV', 'development')
    if env == 'production':
        return ProductionConfig()
    if env == 'testing':
        return TestingConfig()
    return DevelopmentConfig()
