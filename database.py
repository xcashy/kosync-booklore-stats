"""
MySQL database connection and utility functions
"""

import mysql.connector
from mysql.connector import Error
from config import config
import logging

logger = logging.getLogger(__name__)


def get_db_connection():
    """
    Creates a new MySQL connection
    
    Returns:
        mysql.connector.MySQLConnection: The database connection
        
    Raises:
        Error: If connection fails
    """
    try:
        connection = mysql.connector.connect(**config.DB_CONFIG)
        logger.debug("Database connection established")
        return connection
    except Error as e:
        logger.error(f"Database connection failed: {e}", exc_info=True)
        raise


def execute_query(query, params=None, fetch_one=False):
    """
    Executes a SELECT query
    
    Args:
        query (str): SQL query
        params (tuple): Query parameters
        fetch_one (bool): Return only one row
        
    Returns:
        dict or list: Result(s)
    """
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        cursor.execute(query, params or ())
        
        if fetch_one:
            return cursor.fetchone()
        else:
            return cursor.fetchall()
            
    except Error as e:
        logger.error(f"Query error: {e}")
        raise
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


def execute_update(query, params=None):
    """
    Executes an INSERT/UPDATE/DELETE query
    
    Args:
        query (str): SQL query
        params (tuple): Query parameters
        
    Returns:
        int: ID of inserted/updated record
    """
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        cursor.execute(query, params or ())
        connection.commit()
        
        # For INSERT: return last_insert_id
        if 'INSERT' in query.upper():
            return cursor.lastrowid
        
        return cursor.rowcount
            
    except Error as e:
        logger.error(f"Update error: {e}")
        if connection:
            connection.rollback()
        raise
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


# Utility functions for Booklore tables

def get_user_by_username(username):
    """Get a user by username"""
    query = "SELECT * FROM koreader_user WHERE username = %s"
    return execute_query(query, (username,), fetch_one=True)


def get_book_by_id(book_id):
    """Get a book by ID"""
    query = "SELECT * FROM book_file WHERE book_id = %s"
    return execute_query(query, (book_id,), fetch_one=True)


def get_book_info_by_hash(book_hash):
    """
    Get book info (ID and type) by current_hash (book file hash)
    Only returns books that are:
    - Marked as is_book=true in book_file
    - Not deleted in book table
    
    Args:
        book_hash (str): The current_hash value from book_file table
        
    Returns:
        dict: {'book_id': int, 'book_type': str} if found, None otherwise
    """
    query = "SELECT bf.book_id, bf.book_type FROM book_file bf JOIN book b ON bf.book_id = b.id WHERE bf.current_hash = %s AND bf.is_book = 1 AND b.deleted = 0"
    result = execute_query(query, (book_hash,), fetch_one=True)
    if result:
        return {'book_id': result['book_id'], 'book_type': result['book_type']}
    logger.warning(f"Book not found with hash: {book_hash}")
    return None


def insert_completed_session(user_id, book_id, book_type, start_time, end_time, start_progress, end_progress, start_location, end_location):
    """
    Inserts a completed reading session into the database
    
    Args:
        user_id (int): User ID
        book_id (int): Book ID
        book_type (str): Book type (e.g., 'epub')
        start_time (datetime): Session start time
        end_time (datetime): Session end time
        start_progress (float): Starting progress percentage
        end_progress (float): Ending progress percentage
        start_location (str): Starting location/spine
        end_location (str): Ending location/spine
        
    Returns:
        int: Session ID
    """
    # Calculate duration and progress delta
    from datetime import timedelta
    if isinstance(start_time, str):
        from datetime import datetime
        start_time = datetime.fromisoformat(start_time)
    if isinstance(end_time, str):
        from datetime import datetime
        end_time = datetime.fromisoformat(end_time)
    
    duration_seconds = int((end_time - start_time).total_seconds())
    progress_delta = round(float(end_progress) - float(start_progress), config.PROGRESS_DECIMAL_PLACES)
    
    query = """
        INSERT INTO reading_sessions 
        (user_id, book_id, book_type, start_time, end_time, duration_seconds, start_progress, end_progress, progress_delta, start_location, end_location, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    """
    session_id = execute_update(
        query,
        (user_id, book_id, book_type, start_time, end_time, duration_seconds, start_progress, end_progress, progress_delta, start_location, end_location)
    )
    logger.info(f"Completed session {session_id} inserted: user={user_id}, book={book_id}, duration={duration_seconds}s, progress_delta={progress_delta}%")
    return session_id


def create_reading_session(user_id, book_id, book_type, start_progress, start_location):
    """
    Creates a new reading session
    
    Returns:
        int: Session ID
    """
    query = """
        INSERT INTO reading_sessions 
        (user_id, book_id, book_type, start_time, start_progress, start_location, created_at)
        VALUES (%s, %s, %s, NOW(), %s, %s, NOW())
    """
    return execute_update(query, (user_id, book_id, book_type, start_progress, start_location))


def update_reading_session(session_id, end_progress, end_location):
    """
    Updates a reading session with end data
    """
    query = """
        UPDATE reading_sessions
        SET 
            end_time = NOW(),
            end_progress = %s,
            end_location = %s,
            duration_seconds = TIMESTAMPDIFF(SECOND, start_time, NOW()),
            progress_delta = ROUND(%s - start_progress, 1)
        WHERE id = %s
    """
    return execute_update(query, (end_progress, end_location, end_progress, session_id))


def get_active_session(user_id, book_id):
    """
    Gets the active session for a user and book
    (Session without end_time)
    """
    query = """
        SELECT * FROM reading_sessions
        WHERE user_id = %s AND book_id = %s AND end_time IS NULL
        ORDER BY start_time DESC
        LIMIT 1
    """
    return execute_query(query, (user_id, book_id), fetch_one=True)
