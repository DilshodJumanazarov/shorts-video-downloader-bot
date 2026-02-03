#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Lightweight SQLite database for bot statistics
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class Database:
    """Simple database for bot statistics"""

    def __init__(self, db_path: str = "bot_stats.db"):
        """Initialize database"""
        self.db_path = Path(db_path)
        self.conn = None
        self._create_tables()
        logger.info(f"✅ Light Database initialized: {db_path}")

    def _get_connection(self):
        """Get database connection"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def _create_tables(self):
        """Create database tables"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Downloads table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                platform TEXT,
                quality TEXT,
                file_size INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')

        # Errors table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                error_message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        logger.info("✅ Database tables created")

    def add_user(self, user_id: int, username: str):
        """Add or update user"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO users (user_id, username, first_seen, last_seen)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                last_seen = CURRENT_TIMESTAMP
        ''', (user_id, username))

        conn.commit()

    def add_download(self, user_id: int, platform: str, quality: str, file_size: int):
        """Record a download"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO downloads (user_id, platform, quality, file_size)
            VALUES (?, ?, ?, ?)
        ''', (user_id, platform, quality, file_size))

        # Update last_seen
        cursor.execute('''
            UPDATE users SET last_seen = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (user_id,))

        conn.commit()

    def log_error(self, user_id: int, error_message: str):
        """Log an error"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO errors (user_id, error_message)
            VALUES (?, ?)
        ''', (user_id, error_message))

        conn.commit()

    def get_user_stats(self, user_id: int) -> dict:
        """Get user statistics"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Total downloads
        cursor.execute('''
            SELECT COUNT(*) as count FROM downloads WHERE user_id = ?
        ''', (user_id,))
        total = cursor.fetchone()['count']

        # Platform breakdown
        cursor.execute('''
            SELECT platform, COUNT(*) as count
            FROM downloads
            WHERE user_id = ?
            GROUP BY platform
        ''', (user_id,))
        platforms = {row['platform']: row['count'] for row in cursor.fetchall()}

        # Top qualities
        cursor.execute('''
            SELECT quality, COUNT(*) as count
            FROM downloads
            WHERE user_id = ?
            GROUP BY quality
            ORDER BY count DESC
            LIMIT 5
        ''', (user_id,))
        top_qualities = [(row['quality'], row['count']) for row in cursor.fetchall()]

        # Last download
        cursor.execute('''
            SELECT MAX(timestamp) as last_time FROM downloads WHERE user_id = ?
        ''', (user_id,))
        last = cursor.fetchone()['last_time']

        return {
            'downloads': total,
            'youtube': platforms.get('youtube', 0),
            'instagram': platforms.get('instagram', 0),
            'tiktok': platforms.get('tiktok', 0),
            'top_qualities': top_qualities if top_qualities else [('None', 0)],
            'last_download': last or 'Hech qachon',
        }

    def get_global_stats(self) -> dict:
        """Get global statistics"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Total users
        cursor.execute('SELECT COUNT(*) as count FROM users')
        total_users = cursor.fetchone()['count']

        # Total downloads
        cursor.execute('SELECT COUNT(*) as count FROM downloads')
        total_downloads = cursor.fetchone()['count']

        # Platform breakdown
        cursor.execute('''
            SELECT platform, COUNT(*) as count
            FROM downloads
            GROUP BY platform
        ''')
        platforms = {row['platform']: row['count'] for row in cursor.fetchall()}

        # Top qualities
        cursor.execute('''
            SELECT quality, COUNT(*) as count
            FROM downloads
            GROUP BY quality
            ORDER BY count DESC
            LIMIT 5
        ''')
        top_qualities = [(row['quality'], row['count']) for row in cursor.fetchall()]

        # Most used quality
        most_used = top_qualities[0][0] if top_qualities else 'None'

        return {
            'total_users': total_users,
            'total_downloads': total_downloads,
            'youtube': platforms.get('youtube', 0),
            'instagram': platforms.get('instagram', 0),
            'tiktok': platforms.get('tiktok', 0),
            'top_qualities': top_qualities if top_qualities else [('None', 0)],
            'most_used': most_used,
        }

    def get_recent_errors(self, limit: int = 10) -> list:
        """Get recent errors"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT user_id, error_message, timestamp
            FROM errors
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))

        return [
            {
                'user_id': row['user_id'],
                'error_message': row['error_message'],
                'timestamp': row['timestamp'],
            }
            for row in cursor.fetchall()
        ]

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None