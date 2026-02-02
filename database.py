import sqlite3
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Database:
    """Light database - faqat asosiy statistika"""

    def __init__(self, db_name='bot_stats.db'):
        """Database yaratish"""
        try:
            self.conn = sqlite3.connect(db_name, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.create_tables()
            logger.info(f"✅ Light Database initialized: {db_name}")
        except Exception as e:
            logger.error(f"Database error: {e}")

    def create_tables(self):
        """Oddiy jadvallar yaratish"""
        cursor = self.conn.cursor()

        # Users jadvali - faqat asosiy ma'lumot
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                first_seen TEXT,
                last_seen TEXT
            )
        ''')

        # Platform statistikasi - faqat counter
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS platform_stats (
                platform TEXT PRIMARY KEY,
                downloads INTEGER DEFAULT 0
            )
        ''')

        # Quality statistikasi - faqat counter
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quality_stats (
                quality TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0
            )
        ''')

        self.conn.commit()
        logger.info("✅ Database tables created")

    def add_user(self, user_id, username=None, first_name=None):
        """User qo'shish yoki yangilash"""
        try:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()

            # User mavjudligini tekshirish
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            exists = cursor.fetchone()

            if exists:
                # Faqat last_seen yangilash
                cursor.execute('''
                    UPDATE users SET last_seen = ?, username = ?, first_name = ?
                    WHERE user_id = ?
                ''', (now, username, first_name, user_id))
            else:
                # Yangi user qo'shish
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, now, now))

            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False

    def increment_platform(self, platform):
        """Platform counterini oshirish"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO platform_stats (platform, downloads) VALUES (?, 1)
                ON CONFLICT(platform) DO UPDATE SET downloads = downloads + 1
            ''', (platform,))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error incrementing platform: {e}")
            return False

    def increment_quality(self, quality):
        """Quality counterini oshirish"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO quality_stats (quality, count) VALUES (?, 1)
                ON CONFLICT(quality) DO UPDATE SET count = count + 1
            ''', (quality,))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error incrementing quality: {e}")
            return False

    def get_total_users(self):
        """Jami userlar"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting total users: {e}")
            return 0

    def get_total_downloads(self):
        """Jami yuklanishlar"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT SUM(downloads) FROM platform_stats')
            result = cursor.fetchone()[0]
            return result if result else 0
        except Exception as e:
            logger.error(f"Error getting total downloads: {e}")
            return 0

    def get_platform_stats(self):
        """Platform statistikasi"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT platform, downloads 
                FROM platform_stats 
                ORDER BY downloads DESC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting platform stats: {e}")
            return []

    def get_quality_stats(self):
        """Sifat statistikasi"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT quality, count 
                FROM quality_stats 
                ORDER BY count DESC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting quality stats: {e}")
            return []

    def get_recent_users(self, limit=5):
        """Oxirgi userlar"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT user_id, username, first_name, last_seen 
                FROM users 
                ORDER BY last_seen DESC 
                LIMIT ?
            ''', (limit,))
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting recent users: {e}")
            return []

    def close(self):
        """Database yopish"""
        if self.conn:
            self.conn.close()
            logger.info("✅ Database closed")