"""
KoSync Booklore Stats Proxy
A proxy server that sits between Readest and Booklore to track reading sessions.
"""

import os
import signal
import sys
import logging
from dotenv import load_dotenv
from flask import Flask

# Load environment variables
load_dotenv()

# Setup logging before any imports that use logging
from logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# Load configuration from environment variables
from config import config
app.config.from_object(config)

# Register blueprints
from routes import proxy_bp, session_manager
app.register_blueprint(proxy_bp)


def shutdown_handler(signum, frame):
    """Handle shutdown signals - flush active sessions before exit"""
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name}, flushing active sessions...")
    session_manager.flush_all_sessions()
    logger.info("Shutdown complete")
    sys.exit(0)


# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

logger.info("Flask application initialized")

if __name__ == '__main__':
    port = int(os.getenv('FLASK_PORT', 5000))

    logger.info(f"KoSync Proxy starting on http://0.0.0.0:{port}")
    logger.info(f"Booklore KoSync URL: {config.BOOKLORE_KOSYNC_URL}")
    logger.info(f"Session timeout: {config.SESSION_TIMEOUT_MINUTES} minutes")
    logger.info(f"Debug mode: {config.DEBUG}")

    app.run(host='0.0.0.0', port=port, debug=config.DEBUG)
