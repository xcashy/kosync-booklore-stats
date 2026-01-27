"""
Central error handling and custom exception classes
"""

import logging

logger = logging.getLogger(__name__)


class KoSyncProxyException(Exception):
    """Base exception for KoSync Proxy"""
    pass


class BookloreConnectionError(KoSyncProxyException):
    """Exception raised when Booklore connection fails"""
    
    def __init__(self, message, original_error=None):
        self.message = message
        self.original_error = original_error
        logger.error(f"BookloreConnectionError: {message}", exc_info=original_error)
        super().__init__(self.message)


class SessionTrackingError(KoSyncProxyException):
    """Exception raised when session tracking fails"""
    
    def __init__(self, message, original_error=None):
        self.message = message
        self.original_error = original_error
        logger.error(f"SessionTrackingError: {message}", exc_info=original_error)
        super().__init__(self.message)


class DatabaseError(KoSyncProxyException):
    """Exception raised when database operations fail"""
    
    def __init__(self, message, original_error=None):
        self.message = message
        self.original_error = original_error
        logger.error(f"DatabaseError: {message}", exc_info=original_error)
        super().__init__(self.message)


def handle_http_error(status_code, error_message, request_id=None):
    """
    Helper to format HTTP error responses
    
    Args:
        status_code (int): HTTP status code
        error_message (str): Error message
        request_id (str): Request ID for logging correlation
        
    Returns:
        tuple: (response_dict, status_code)
    """
    response = {'error': error_message}
    if request_id:
        response['request_id'] = request_id
    
    return response, status_code
