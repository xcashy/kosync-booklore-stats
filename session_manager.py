"""
Session management and tracking
Manages active reading sessions and stores them in the database
"""

import logging
from datetime import datetime, timezone
from threading import Timer, Lock
from database import (
    get_user_by_username,
    get_book_info_by_hash,
    insert_completed_session
)
from config import config

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages reading sessions for users"""
    
    def __init__(self):
        # Dict: {(user_id, book_id): {
        #   'start_time': datetime,
        #   'start_progress': float,
        #   'current_progress': float,
        #   'start_location': str,
        #   'current_location': str,
        #   'timeout_timer': Timer,
        #   'last_update': datetime
        # }}
        # Sessions are only written to DB when they complete (timeout)
        self.active_sessions = {}
        self._lock = Lock()
        self.timeout_minutes = config.SESSION_TIMEOUT_MINUTES
    
    
    def handle_sync(self, method, username, book_hash, progress=0, location='', device='', device_id=''):
        """
        Processes a KoSync request (GET or PUT)
        
        Args:
            method (str): 'GET' or 'PUT'
            username (str): Username from x-auth-user header
            book_hash (str): Book hash (current_hash from book_file table)
            progress (float): Progress percentage (0.0-100.0)
            location (str): Current progress location/spine
            device (str): Device name
            device_id (str): Device ID
        """
        try:
            # Find user in database
            user = get_user_by_username(username)
            if not user:
                logger.warning(f"User {username} not found in database")
                return
            
            user_id = user['id']
            
            # Find book by hash
            book_info = get_book_info_by_hash(book_hash)
            if not book_info:
                logger.warning(f"Book with hash {book_hash} not found in database")
                return
            
            book_id = book_info['book_id']
            book_type = book_info['book_type']
            
            # Session key
            session_key = (user_id, book_id)
            
            # Ensure progress is a float
            try:
                progress = float(progress)
            except (ValueError, TypeError):
                progress = 0
                logger.warning(f"Invalid progress value for user {username}, book {book_hash}")
            
            # Handle session based on request type
            if method == 'PUT':
                # PUT = Progress update → update or start session
                self._handle_put(session_key, user_id, book_id, book_type, progress, location)
            elif method == 'GET':
                # GET = Get progress → keep session alive or start new one
                self._handle_get(session_key, user_id, book_id, book_type, progress, location)
            
        except Exception as e:
            logger.error(f"Error handling session: {e}", exc_info=True)
    
    
    def _handle_put(self, session_key, user_id, book_id, book_type, progress, location):
        """
        Handles PUT requests (progress updates)
        Creates or updates in-memory session tracking
        Sessions are NOT written to database until timeout (completion)
        """
        now = datetime.now(timezone.utc)

        with self._lock:
            if session_key in self.active_sessions:
                # Session exists - update and reset timeout
                session_info = self.active_sessions[session_key]

                # Cancel old timer
                if session_info['timeout_timer']:
                    session_info['timeout_timer'].cancel()

                # Update session data in memory
                session_info['current_progress'] = progress
                session_info['current_location'] = location
                session_info['last_update'] = now

                logger.info(f"Session for user={user_id}, book={book_id} updated in memory: progress={progress}%, location={location}")

            else:
                # No active session - create new internal session
                logger.info(f"New session created in memory: user={user_id}, book={book_id}, start_progress={progress}%")
                self.active_sessions[session_key] = {
                    'start_time': now,
                    'start_progress': progress,
                    'current_progress': progress,
                    'start_location': location,
                    'current_location': location,
                    'book_type': book_type,
                    'timeout_timer': None,
                    'last_update': now
                }

            # Start new timeout timer
            timer = Timer(
                self.timeout_minutes * 60,
                self._timeout_session,
                args=[session_key]
            )
            timer.daemon = True
            timer.start()

            self.active_sessions[session_key]['timeout_timer'] = timer
    
    
    def _handle_get(self, session_key, user_id, book_id, book_type, progress, location):
        """
        Handles GET requests (get progress)
        Keeps active sessions or creates new ones if not existing
        """
        now = datetime.now(timezone.utc)

        with self._lock:
            if session_key in self.active_sessions:
                # Session exists - reset timeout
                session_info = self.active_sessions[session_key]

                if session_info['timeout_timer']:
                    session_info['timeout_timer'].cancel()

                logger.debug(f"GET: Session for user={user_id}, book={book_id} kept alive")

            else:
                # No active session - create new one
                logger.info(f"GET: New session created in memory: user={user_id}, book={book_id}, start_progress={progress}%")
                self.active_sessions[session_key] = {
                    'start_time': now,
                    'start_progress': progress,
                    'current_progress': progress,
                    'start_location': location,
                    'current_location': location,
                    'book_type': book_type,
                    'timeout_timer': None,
                    'last_update': now
                }

            # Start new timeout timer
            timer = Timer(
                self.timeout_minutes * 60,
                self._timeout_session,
                args=[session_key]
            )
            timer.daemon = True
            timer.start()

            self.active_sessions[session_key]['timeout_timer'] = timer
    
    
    def _timeout_session(self, session_key):
        """
        Called when a session times out (after inactivity)
        Writes the completed session to the database
        """
        # Extract session data under lock, then release before DB write
        with self._lock:
            if session_key not in self.active_sessions:
                return

            session_info = self.active_sessions.pop(session_key)

        user_id, book_id = session_key

        try:
            # Get session data from memory
            start_time = session_info.get('start_time')
            end_time = session_info.get('last_update', start_time)
            start_progress = session_info.get('start_progress', 0)
            end_progress = session_info.get('current_progress', start_progress)
            start_location = session_info.get('start_location', '')
            end_location = session_info.get('current_location', start_location)

            # Only write to database if session meets criteria:
            # 1. At least minimum duration (configurable, default 10s)
            # 2. Progress changed (end_progress != start_progress)
            duration_seconds = (end_time - start_time).total_seconds()
            progress_delta = end_progress - start_progress
            min_duration = config.SESSION_MIN_DURATION_SECONDS

            if duration_seconds >= min_duration and progress_delta != 0:
                # Write completed session to database
                # Convert progress from decimal (0.0-1.0) to percentage (0-100)
                book_type = session_info.get('book_type', 'EPUB')
                start_progress_pct = round(start_progress * 100, config.PROGRESS_DECIMAL_PLACES)
                end_progress_pct = round(end_progress * 100, config.PROGRESS_DECIMAL_PLACES)
                session_id = insert_completed_session(
                    user_id=user_id,
                    book_id=book_id,
                    book_type=book_type,
                    start_time=start_time,
                    end_time=end_time,
                    start_progress=start_progress_pct,
                    end_progress=end_progress_pct,
                    start_location=start_location,
                    end_location=end_location
                )
                logger.info(f"Session {session_id} completed and written to DB: user={user_id}, book={book_id}, duration={duration_seconds}s, progress {start_progress_pct:.1f}% → {end_progress_pct:.1f}%")
            else:
                reason = []
                if duration_seconds < min_duration:
                    reason.append(f"duration {duration_seconds}s < {min_duration}s")
                if progress_delta == 0:
                    reason.append(f"no position change ({start_progress * 100:.1f}%)")
                logger.debug(f"Session for user={user_id}, book={book_id} not written to DB: {', '.join(reason)}")

        except Exception as e:
            logger.error(f"Error writing completed session to database: {e}", exc_info=True)

    def flush_all_sessions(self):
        """
        Flush all active sessions to database (called on shutdown)
        """
        with self._lock:
            if not self.active_sessions:
                logger.info("Shutdown: No active sessions to flush")
                return

            sessions_to_flush = list(self.active_sessions.items())
            # Cancel all timers and clear dict
            for session_key, session_info in sessions_to_flush:
                if session_info.get('timeout_timer'):
                    session_info['timeout_timer'].cancel()
            self.active_sessions.clear()

        logger.info(f"Shutdown: Flushing {len(sessions_to_flush)} active session(s) to database")

        for session_key, session_info in sessions_to_flush:
            user_id, book_id = session_key
            try:
                start_time = session_info.get('start_time')
                end_time = session_info.get('last_update', start_time)
                start_progress = session_info.get('start_progress', 0)
                end_progress = session_info.get('current_progress', start_progress)
                start_location = session_info.get('start_location', '')
                end_location = session_info.get('current_location', start_location)

                duration_seconds = (end_time - start_time).total_seconds()
                progress_delta = end_progress - start_progress
                min_duration = config.SESSION_MIN_DURATION_SECONDS

                if duration_seconds >= min_duration and progress_delta != 0:
                    book_type = session_info.get('book_type', 'EPUB')
                    start_progress_pct = round(start_progress * 100, config.PROGRESS_DECIMAL_PLACES)
                    end_progress_pct = round(end_progress * 100, config.PROGRESS_DECIMAL_PLACES)
                    session_id = insert_completed_session(
                        user_id=user_id,
                        book_id=book_id,
                        book_type=book_type,
                        start_time=start_time,
                        end_time=end_time,
                        start_progress=start_progress_pct,
                        end_progress=end_progress_pct,
                        start_location=start_location,
                        end_location=end_location
                    )
                    logger.info(f"Shutdown: Session {session_id} flushed to DB: user={user_id}, book={book_id}")
                else:
                    logger.debug(f"Shutdown: Session for user={user_id}, book={book_id} skipped (criteria not met)")

            except Exception as e:
                logger.error(f"Shutdown: Error flushing session for user={user_id}, book={book_id}: {e}")
