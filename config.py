"""
Flask Configuration
"""

import os


class Config:
    """Application configuration"""

    # Flask
    DEBUG = os.getenv('FLASK_DEBUG', 'False') == 'True'

    # Booklore KoSync Server
    BOOKLORE_KOSYNC_URL = os.getenv('BOOKLORE_KOSYNC_URL', 'http://booklore:6060/api/kosync')

    # Session tracking
    SESSION_TIMEOUT_MINUTES = int(os.getenv('SESSION_TIMEOUT_MINUTES', 10))
    SESSION_MIN_DURATION_SECONDS = int(os.getenv('SESSION_MIN_DURATION_SECONDS', 10))
    PROGRESS_DECIMAL_PLACES = int(os.getenv('PROGRESS_DECIMAL_PLACES', 1))

    # Database
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', 'mariadb'),
        'port': int(os.getenv('DB_PORT', 3306)),
        'user': os.getenv('DB_USER', 'booklore'),
        'password': os.getenv('DB_PASSWORD', 'password'),
        'database': os.getenv('DB_NAME', 'booklore'),
    }


config = Config()
