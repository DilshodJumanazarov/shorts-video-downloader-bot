#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shorts Video Downloader Bot
Supports: YouTube Shorts, Instagram Reels, TikTok
"""

import os
import logging
import re
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
import yt_dlp

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============================================================================
# CONFIGURATION
# ============================================================================

BOT_TOKEN = os.getenv('BOT_TOKEN', '8341836427:AAHzwfnI68RJawROjOfHCwgAtkSQjvUg8nk')
ADMIN_ID = int(os.getenv('ADMIN_ID', '6351892611'))

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Download directory
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Platform detection patterns
PLATFORM_PATTERNS = {
    'youtube': r'(youtube\.com/shorts/|youtu\.be/)',
    'instagram': r'(instagram\.com/reel/|instagram\.com/p/)',
    'tiktok': r'(tiktok\.com/@[\w\.]+/video/|vm\.tiktok\.com/|vt\.tiktok\.com/)',
}

# Quality presets
QUALITY_PRESETS = {
    '144p': {'height': 144, 'label': '144p'},
    '360p': {'height': 360, 'label': '360p'},
    '480p': {'height': 480, 'label': '480p (SD)'},
    '720p': {'height': 720, 'label': '720p (HD)'},
    '1080p': {'height': 1080, 'label': '1080p (Full HD)'},
}

# Rate limiting
user_last_download = {}
RATE_LIMIT_SECONDS = 12

# ============================================================================
# DATABASE
# ============================================================================

try:
    from database import Database

    db = Database()
    logger.info("✅ Light Database initialized")
except Exception as e:
    logger.error(f"❌ Database error: {e}")
    db = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def detect_platform(url: str) -> Optional[str]:
    """Detect platform from URL"""
    for platform, pattern in PLATFORM_PATTERNS.items():
        if re.search(pattern, url, re.IGNORECASE):
            return platform
    return None


def is_shorts_url(url: str) -> bool:
    """Check if URL is a short-form video"""
    shorts_patterns = [
        r'youtube\.com/shorts/',
        r'instagram\.com/reel/',
        r'tiktok\.com/@[\w\.]+/video/',
        r'vm\.tiktok\.com/',
        r'vt\.tiktok\.com/',
    ]
    return any(re.search(pattern, url, re.IGNORECASE) for pattern in shorts_patterns)


def format_size(size_bytes: int) -> str:
    """Format file size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"


def sanitize_filename(filename: str) -> str:
    """Sanitize filename"""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)[:100]


# ============================================================================
# COMMAND HANDLERS
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user

    if db:
        db.add_user(user.id, user.username or "Unknown")

    logger.info(f"👤 User {user.id} (@{user.username}) started bot")

    start_text = """
🎬 <b>Salom! Shorts Video Downloader Botga xush kelibsiz!</b>

📌 <b>Qanday ishlaydi:</b>
1️⃣ Faqat Shorts video linkini yuboring
2️⃣ Sifatni tanlang
3️⃣ Videoni yuklab oling!

✅ <b>Qo'llab-quvvatlanadigan formatlar:</b>
• YouTube Shorts
• Instagram Reels
• TikTok videolar

⚠️ <b>Muhim:</b> Faqat qisqa videolar (Shorts/Reels) yuklanadi. Oddiy uzun YouTube videolar qabul qilinmaydi.

📊 <b>Yordam:</b> /help
"""

    # BUTTON O'CHIRILDI - faqat text
    await update.message.reply_text(start_text, parse_mode='HTML')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
📚 <b>YORDAM - QANDAY ISHLAYDI?</b>

🎬 <b>Qo'llab-quvvatlanadigan formatlar:</b>
• YouTube Shorts
• Instagram Reels
• TikTok videolar

📝 <b>Ishlatish:</b>
1️⃣ Faqat Shorts video linkini yuboring
2️⃣ Sifatni tanlang
3️⃣ Videoni yuklab oling!

⚙️ <b>Sifat tanlovi:</b>
• 144p - Eng yengil
• 360p - Yaxshi
• 480p - SD
• 720p - HD
• 1080p - Full HD

⚠️ <b>Muhim:</b>
• Faqat qisqa videolar (Shorts/Reels) yuklanadi
• Oddiy uzun YouTube videolar qabul qilinmaydi

💬 <b>Yordam kerakmi?</b>
Admin: @d_jumanazarov

📊 <b>Boshqa komandalar:</b>
/mystat - Sizning statistikangiz
"""

    await update.message.reply_text(help_text, parse_mode='HTML')


async def mystat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics"""
    user_id = update.effective_user.id

    if not db:
        await update.message.reply_text("❌ Statistika mavjud emas")
        return

    stats = db.get_user_stats(user_id)

    stat_text = f"""
📊 <b>Sizning statistikangiz:</b>

📥 Jami yuklashlar: {stats['downloads']}
🎬 YouTube: {stats['youtube']}
📸 Instagram: {stats['instagram']}
🎵 TikTok: {stats['tiktok']}
🔝 Top 5 sifatlar:
"""

    for quality, count in stats['top_qualities']:
        stat_text += f"• {quality}: {count}\n"

    stat_text += f"\n🕐 {stats['last_download']}"

    await update.message.reply_text(stat_text, parse_mode='HTML')


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin statistics (Admin only)"""
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔️ Bu komanda faqat admin uchun!")
        return

    if not db:
        await update.message.reply_text("❌ Statistika mavjud emas")
        return

    stats = db.get_global_stats()

    stat_text = f"""
📊 <b>GLOBAL STATISTIKA</b>

👥 Jami foydalanuvchilar: {stats['total_users']}
📥 Jami yuklashlar: {stats['total_downloads']}

📊 Platformalar:
• YouTube: {stats['youtube']}
• Instagram: {stats['instagram']}
• TikTok: {stats['tiktok']}

🎬 Top 5 Sifatlar:
"""

    for quality, count in stats['top_qualities']:
        stat_text += f"• {quality}: {count}\n"

    stat_text += f"\n• Eng yaxshi: {stats['most_used']}\n"

    await update.message.reply_text(stat_text, parse_mode='HTML')


async def errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent errors (Admin only)"""
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔️ Bu komanda faqat admin uchun!")
        return

    if not db:
        await update.message.reply_text("❌ Xatoliklar mavjud emas")
        return

    errors = db.get_recent_errors(limit=10)

    if not errors:
        await update.message.reply_text("✅ Hech qanday xatolik yo'q!")
        return

    error_text = "❌ <b>OXIRGI XATOLIKLAR:</b>\n\n"

    for error in errors:
        error_text += f"🕐 {error['timestamp']}\n"
        error_text += f"👤 User: {error['user_id']}\n"
        error_text += f"⚠️ {error['error_message'][:100]}...\n\n"

    await update.message.reply_text(error_text, parse_mode='HTML')


# ============================================================================
# BUTTON CALLBACK HANDLER
# ============================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks"""
    query = update.callback_query
    await query.answer()

    data = query.data

    # Quality selection
    if data.startswith("quality_"):
        await quality_selected(update, context)
        return

# ============================================================================
# URL HANDLER
# ============================================================================

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video URL"""
    user_id = update.effective_user.id
    url = update.message.text.strip()

    logger.info(f"📥 User {user_id} sent URL: {url[:50]}...")

    # Check if URL is valid
    platform = detect_platform(url)

    if not platform:
        await update.message.reply_text(
            "❌ Link tanilmadi!\n\n"
            "✅ Qo'llab-quvvatlanadigan:\n"
            "• YouTube Shorts\n"
            "• Instagram Reels\n"
            "• TikTok videolar"
        )
        return

    # Check if it's a shorts URL
    if not is_shorts_url(url):
        await update.message.reply_text(
            "❌ Faqat qisqa videolar (Shorts/Reels) qo'llab-quvvatlanadi!\n\n"
            "Oddiy uzun YouTube videolar yuklanmaydi."
        )
        return

    logger.info(f"📊 Detected: {platform.upper()} - shorts")

    # Rate limiting
    now = datetime.now().timestamp()
    last_time = user_last_download.get(user_id, 0)

    if now - last_time < RATE_LIMIT_SECONDS:
        wait_time = int(RATE_LIMIT_SECONDS - (now - last_time))
        await update.message.reply_text(
            f"⏳ Iltimos {wait_time} soniya kuting!"
        )
        return

    # Store URL in context
    context.user_data['url'] = url
    context.user_data['platform'] = platform

    # Show quality options
    keyboard = [
        [
            InlineKeyboardButton("144p", callback_data="quality_144p"),
            InlineKeyboardButton("360p", callback_data="quality_360p"),
        ],
        [
            InlineKeyboardButton("480p (SD)", callback_data="quality_480p"),
            InlineKeyboardButton("720p (HD)", callback_data="quality_720p"),
        ],
        [
            InlineKeyboardButton("1080p (Full HD)", callback_data="quality_1080p"),
        ],
    ]

    await update.message.reply_text(
        f"✅ {platform.upper()} video topildi!\n\n"
        "📊 Sifatni tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================================
# QUALITY SELECTION AND DOWNLOAD
# ============================================================================

async def quality_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quality selection"""
    query = update.callback_query
    user_id = query.from_user.id
    quality = query.data.replace("quality_", "")

    url = context.user_data.get('url')
    platform = context.user_data.get('platform')

    if not url:
        await query.answer("❌ Xatolik: URL topilmadi")
        await query.message.reply_text("❌ Xatolik: URL topilmadi. Qaytadan link yuboring.")
        return

    # Answer callback first
    await query.answer(f"⏳ {quality} yuklanmoqda...")

    # Send loading message (NEW MESSAGE, not edit!)
    loading_msg = await query.message.reply_text(f"⏳ {quality} yuklanmoqda...")

    # Update rate limit
    user_last_download[user_id] = datetime.now().timestamp()

    # Download video
    try:
        video_path, title, height, width, duration = await download_video(
            url, quality, user_id, platform
        )

        # Determine orientation
        is_vertical = height > width
        orientation = "Vertikal" if is_vertical else "Gorizontal"

        file_size = os.path.getsize(video_path)
        size_str = format_size(file_size)

        logger.info(f"📊 {platform.upper()} | {orientation} | {width}x{height} | {size_str} | {duration:.3f}s")

        # Delete loading message
        await loading_msg.delete()

        # Send video
        with open(video_path, 'rb') as video_file:
            caption = f"📹 {title[:100]}\n📊 {width}x{height} | {size_str}"

            await query.message.reply_video(
                video=video_file,
                caption=caption,
                supports_streaming=True,
                width=width,
                height=height,
                duration=int(duration)
            )

        # Delete file
        os.remove(video_path)
        logger.info(f"🗑 Deleted file: {video_path}")

        # Save to database
        if db:
            db.add_download(user_id, platform, quality, file_size)

        # Success message
        await query.message.reply_text(
            f"✅ {quality} → {width}x{height} | {size_str}"
        )

        logger.info(f"✅ {quality} → {width}x{height} | {size_str}")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ quality_selected error: {error_msg}")

        # Delete loading message
        try:
            await loading_msg.delete()
        except:
            pass

        if db:
            db.log_error(user_id, error_msg)

        await query.message.reply_text(
            f"❌ Xatolik: {error_msg[:200]}\n\n"
            "Qaytadan urinib ko'ring yoki boshqa link yuboring."
        )


async def download_video(url: str, quality: str, user_id: int, platform: str) -> Tuple[str, str, int, int, float]:
    """Download video with yt-dlp"""
    timestamp = int(datetime.now().timestamp())
    output_template = str(DOWNLOAD_DIR / f"{user_id}_{timestamp}_%(id)s.%(ext)s")

    # Quality format
    max_height = QUALITY_PRESETS[quality]['height']
    format_choice = f'best[height<={max_height}][ext=mp4]/best[height<={max_height}]/best'

    # yt-dlp options
    ydl_opts = {
        'format': format_choice,
        'outtmpl': output_template,

        # YouTube bot detection bypass
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web'],
                'skip': ['hls', 'dash'],
                'player_skip': ['webpage', 'configs'],
            }
        },

        # Better headers
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        },

        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 90,
        'retries': 5,
        'fragment_retries': 5,
        'merge_output_format': 'mp4',
        'prefer_ffmpeg': True,
        'http_chunk_size': 10485760,
        'nocheckcertificate': True,
        'age_limit': None,
    }

    def download():
        """Sync download function"""
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            # Get video info
            title = sanitize_filename(info.get('title', 'video'))
            video_id = info.get('id', 'unknown')
            ext = info.get('ext', 'mp4')

            # Get actual file path
            video_path = DOWNLOAD_DIR / f"{user_id}_{timestamp}_{video_id}.{ext}"

            # Get dimensions
            width = info.get('width', 0)
            height = info.get('height', 0)
            duration = info.get('duration', 0)

            return str(video_path), title, height, width, duration

    # Run in executor with retries
    loop = asyncio.get_event_loop()
    max_retries = 3

    for attempt in range(max_retries):
        try:
            result = await loop.run_in_executor(None, download)
            return result
        except Exception as e:
            logger.error(f"Download error: {e}")
            if attempt < max_retries - 1:
                logger.warning(f"Download failed, retry {attempt + 1}/{max_retries}")
                await asyncio.sleep(2 ** attempt)
            else:
                raise


# ============================================================================
# ECHO HANDLER
# ============================================================================

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-URL messages"""
    await update.message.reply_text(
        "❓ Link tanilmadi!\n\n"
        "📌 Quyidagi formatlardan birini yuboring:\n"
        "• YouTube Shorts\n"
        "• Instagram Reels\n"
        "• TikTok videolar\n\n"
        "📊 Yordam: /help"
    )


# ============================================================================
# ERROR HANDLER
# ============================================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error("❌ Exception while handling an update:", exc_info=context.error)
    logger.error(f"Full traceback:\n{context.error}")

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.\n\n"
                "Agar muammo davom etsa, admin bilan bog'laning: @d_jumanazarov"
            )
        except Exception:
            pass


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Start the bot"""
    logger.info("✅ Config loaded. Admin ID: %d", ADMIN_ID)
    logger.info("🚀 Initializing bot...")

    # Start health check server
    try:
        from healthcheck import start_health_check_server
        start_health_check_server()
        logger.info("✅ Health check server started on port 8080")
    except Exception as e:
        logger.warning(f"⚠️ Health check server not started: {e}")

    # Create application
    app = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    app.add_error_handler(error_handler)
    logger.info("✅ Error handler registered")

    app.add_handler(CommandHandler("start", start_command))
    logger.info("✅ /start handler registered")

    app.add_handler(CommandHandler("help", help_command))
    logger.info("✅ /help handler registered")

    app.add_handler(CommandHandler("stats", stats_command))
    logger.info("✅ /stats handler registered")

    app.add_handler(CommandHandler("mystat", mystat_command))
    logger.info("✅ /mystat handler registered")

    app.add_handler(CommandHandler("errors", errors_command))
    logger.info("✅ /errors handler registered")

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'http'), handle_url))
    logger.info("✅ Link handler registered")

    app.add_handler(CallbackQueryHandler(button_callback))
    logger.info("✅ Quality handler registered")

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    logger.info("✅ Echo handler registered")

    logger.info("🤖 Bot ishga tushdi!")
    logger.info("✅ Error handling enabled")
    logger.info("✅ Auto-retry enabled")
    logger.info("✅ Health check enabled")

    # Start polling
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.critical(f"❌ CRITICAL ERROR in main(): {e}", exc_info=True)
        raise