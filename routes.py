"""
Proxy routes for KoSync API
Forwards requests to Booklore and tracks reading sessions
"""

from flask import Blueprint, request, jsonify
import requests
import logging
import uuid
from config import config
from session_manager import SessionManager

logger = logging.getLogger(__name__)
proxy_bp = Blueprint('proxy', __name__, url_prefix='')
session_manager = SessionManager()


@proxy_bp.before_request
def before_request():
    """Hook before each request - initialize request logging"""
    request.request_id = str(uuid.uuid4())[:8]
    logger.debug(f"[{request.request_id}] {request.method} {request.path} from {request.remote_addr}")


@proxy_bp.after_request
def after_request(response):
    """Hook after each request - log response"""
    logger.debug(f"[{request.request_id}] Response status: {response.status_code}")
    return response


@proxy_bp.route('/syncs/progress', methods=['PUT'])
def update_progress():
    """
    PUT /syncs/progress
    Update reading progress for a document
    
    Required headers:
        - x-auth-user: Username
        - x-auth-key: Authentication key
        
    Required payload:
        - document: Book hash (current_hash from book_file)
        - progress: Current progress location
        - percentage: Progress percentage (0.0-100.0)
        - device: Device name
        - device_id: Device identifier
    """
    try:
        # Extract auth headers
        username = request.headers.get('x-auth-user')
        auth_key = request.headers.get('x-auth-key')
        
        if not username or not auth_key:
            logger.warning(f"[{request.request_id}] Missing auth headers")
            return {'error': 'Missing authentication headers'}, 401
        
        # Get payload
        payload = request.get_json() or {}
        logger.debug(f"[{request.request_id}] Update progress payload: {payload}")
        
        # Validate required parameters
        required_params = ['document', 'progress', 'percentage', 'device', 'device_id']
        missing = [p for p in required_params if p not in payload]
        if missing:
            logger.warning(f"[{request.request_id}] Missing required params: {missing}")
            return {'error': f'Missing required parameters: {missing}'}, 400
        
        # Forward request to Booklore with original auth headers
        booklore_url = f"{config.BOOKLORE_KOSYNC_URL}/syncs/progress"
        headers = {
            'x-auth-user': username,
            'x-auth-key': auth_key,
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.put(booklore_url, json=payload, headers=headers, timeout=10)
        except requests.exceptions.Timeout:
            logger.error(f"[{request.request_id}] Timeout connecting to Booklore at {booklore_url}")
            return {'error': 'Booklore connection timeout'}, 504
        except requests.exceptions.ConnectionError:
            logger.error(f"[{request.request_id}] Connection error to Booklore at {booklore_url}")
            return {'error': 'Cannot connect to Booklore'}, 502
        except requests.RequestException as e:
            logger.error(f"[{request.request_id}] Request error: {e}")
            return {'error': 'Request error to Booklore'}, 502
        
        # Check response status
        if response.status_code not in [200, 202, 401]:
            logger.warning(f"[{request.request_id}] Booklore returned status {response.status_code}")
            return response.json() if response.headers.get('content-type') == 'application/json' else {}, response.status_code
        
        # On successful response: track session
        if response.status_code in [200, 202]:
            try:
                session_manager.handle_sync(
                    method='PUT',
                    username=username,
                    book_hash=payload.get('document'),
                    progress=payload.get('percentage'),
                    location=payload.get('progress'),
                    device=payload.get('device'),
                    device_id=payload.get('device_id')
                )
            except Exception as e:
                logger.warning(f"[{request.request_id}] Session tracking error: {e}", exc_info=True)
                # Don't block - response will be returned anyway
        
        logger.info(f"[{request.request_id}] Successfully proxied PUT progress update for {payload.get('document')}")
        return response.json(), response.status_code
        
    except Exception as e:
        logger.error(f"[{request.request_id}] Unexpected error in update_progress: {e}", exc_info=True)
        return {'error': 'Internal server error'}, 500


@proxy_bp.route('/syncs/progress/<book_hash>', methods=['GET'])
def get_progress(book_hash):
    """
    GET /syncs/progress/:document
    Get reading progress for a document
    
    URL parameters:
        - document: Book hash (current_hash from book_file)
        
    Required headers:
        - x-auth-user: Username
        - x-auth-key: Authentication key
    """
    try:
        # Extract auth headers
        username = request.headers.get('x-auth-user')
        auth_key = request.headers.get('x-auth-key')
        
        if not username or not auth_key:
            logger.warning(f"[{request.request_id}] Missing auth headers")
            return {'error': 'Missing authentication headers'}, 401
        
        logger.debug(f"[{request.request_id}] Get progress for document: {book_hash}")
        
        # Forward request to Booklore with original auth headers
        booklore_url = f"{config.BOOKLORE_KOSYNC_URL}/syncs/progress/{book_hash}"
        headers = {
            'x-auth-user': username,
            'x-auth-key': auth_key
        }
        
        try:
            response = requests.get(booklore_url, headers=headers, timeout=10)
        except requests.exceptions.Timeout:
            logger.error(f"[{request.request_id}] Timeout connecting to Booklore at {booklore_url}")
            return {'error': 'Booklore connection timeout'}, 504
        except requests.exceptions.ConnectionError:
            logger.error(f"[{request.request_id}] Connection error to Booklore at {booklore_url}")
            return {'error': 'Cannot connect to Booklore'}, 502
        except requests.RequestException as e:
            logger.error(f"[{request.request_id}] Request error: {e}")
            return {'error': 'Request error to Booklore'}, 502
        
        # Check response status
        if response.status_code not in [200, 401]:
            logger.warning(f"[{request.request_id}] Booklore returned status {response.status_code}")
            return response.json() if response.headers.get('content-type') == 'application/json' else {}, response.status_code
        
        # On successful response: track that session is active
        if response.status_code == 200:
            try:
                data = response.json()
                session_manager.handle_sync(
                    method='GET',
                    username=username,
                    book_hash=book_hash,
                    progress=data.get('percentage', 0),
                    location=data.get('progress', '')
                )
            except Exception as e:
                logger.warning(f"[{request.request_id}] Session tracking error: {e}", exc_info=True)
        
        logger.info(f"[{request.request_id}] Successfully proxied GET progress for {book_hash}")
        return response.json(), response.status_code
        
    except Exception as e:
        logger.error(f"[{request.request_id}] Unexpected error in get_progress: {e}", exc_info=True)
        return {'error': 'Internal server error'}, 500


@proxy_bp.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
def proxy_all(path):
    """
    Catch-all proxy handler for unknown endpoints
    Forwards all unhandled requests to Booklore
    """
    try:
        # Build Booklore URL
        booklore_url = f"{config.BOOKLORE_KOSYNC_URL}/{path}"
        if request.query_string:
            booklore_url += f"?{request.query_string.decode('utf-8')}"
        
        # Copy headers from original request (except host)
        headers = {}
        for header, value in request.headers:
            if header.lower() not in ['host', 'connection']:
                headers[header] = value
        
        logger.debug(f"[{request.request_id}] Proxying {request.method} {path} to Booklore")
        
        try:
            # Forward request to Booklore
            response = requests.request(
                method=request.method,
                url=booklore_url,
                headers=headers,
                data=request.get_data(),
                allow_redirects=False,
                timeout=10
            )
        except requests.exceptions.Timeout:
            logger.error(f"[{request.request_id}] Timeout connecting to Booklore at {booklore_url}")
            return {'error': 'Booklore connection timeout'}, 504
        except requests.exceptions.ConnectionError:
            logger.error(f"[{request.request_id}] Connection error to Booklore at {booklore_url}")
            return {'error': 'Cannot connect to Booklore'}, 502
        except requests.RequestException as e:
            logger.error(f"[{request.request_id}] Request error: {e}")
            return {'error': 'Request error to Booklore'}, 502
        
        logger.info(f"[{request.request_id}] Successfully proxied {request.method} {path} (status {response.status_code})")
        
        # Return response from Booklore
        try:
            return response.json(), response.status_code
        except:
            return response.content, response.status_code
        
    except Exception as e:
        logger.error(f"[{request.request_id}] Unexpected error in proxy_all: {e}", exc_info=True)
        return {'error': 'Internal server error'}, 500


@proxy_bp.errorhandler(500)
def internal_error(error):
    """500 handler for internal errors"""
    logger.error(f"[{request.request_id}] 500 - Internal error: {error}", exc_info=True)
    return {'error': 'Internal server error'}, 500
