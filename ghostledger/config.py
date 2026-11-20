import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
basedir = Path(__file__).resolve().parent.parent
load_dotenv(basedir / '.env')


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'ghostledger-default-secret-key-insecure-only-for-dev')
    
    # Database connection with SQLite fallback
    DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{basedir / "ghostledger.db"}')
    # Normalize postgres/mysql URLs if needed
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
    } if not DATABASE_URL.startswith("sqlite") else {}

    # File uploads
    UPLOAD_FOLDER = basedir / "uploads"
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 10 * 1024 * 1024))  # 10 MB limit
    ALLOWED_EXTENSIONS = {'csv'}

    # LLM Settings
    LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'none').lower().strip()
    LLM_API_KEY = os.getenv('LLM_API_KEY', '').strip()
    LLM_MODEL = os.getenv('LLM_MODEL', 'gpt-4o-mini')
    LLM_TEMPERATURE = float(os.getenv('LLM_TEMPERATURE', '0.0'))

    # Application settings
    DEMO_MODE = os.getenv('DEMO_MODE', 'true').lower() in ('true', '1', 'yes')
    RATE_LIMIT_PER_MINUTE = int(os.getenv('RATE_LIMIT_PER_MINUTE', 60))


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    # In-memory SQLite for high-speed isolated tests
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    DEMO_MODE = True
    LLM_PROVIDER = 'none'
    LLM_API_KEY = ''


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    DEMO_MODE = False
    # In production, require secure SECRET_KEY
    if os.getenv('SECRET_KEY') is None:
        pass  # In prod warning or exception
