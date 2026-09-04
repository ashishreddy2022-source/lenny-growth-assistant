"""
Database package exports.
"""

from app.db.connection import close_db_pool, get_db_pool, init_db_pool, set_db_pool
from app.db.repository import (
    create_session,
    delete_session,
    get_session,
    get_session_messages,
    list_sessions,
    probe_database_and_vectors,
    save_artifact,
    save_message,
    touch_session,
    update_session_title,
)

__all__ = [
    "init_db_pool",
    "close_db_pool",
    "get_db_pool",
    "set_db_pool",
    "create_session",
    "list_sessions",
    "get_session",
    "update_session_title",
    "touch_session",
    "delete_session",
    "save_message",
    "get_session_messages",
    "save_artifact",
    "probe_database_and_vectors",
]
