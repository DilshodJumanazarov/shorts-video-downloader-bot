import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import asyncio
import time
from collections import defaultdict
from datetime import datetime
import traceback
from database import Database
import threading
from healthcheck import start_health_server

# ==================== LOGGING ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger('yt_dlp').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)

# ==================== CONFIG ====================
# Local uchun default token, Railway'da environment variable
BOT_TOKEN = os.getenv('BOT_TOKEN', '8341836427:AAFwmm8aoTwo-HiD8h3CBDyGmxF-3ObL78M')
ADMIN_IDS = [int(os.getenv('ADMIN_ID', '6351892611'))]

if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN topilmadi!")
    raise ValueError("BOT_TOKEN o'rnatilmagan!")

logger.info(f"✅ Config loaded. Admin ID: {ADMIN_IDS[0]}")

# ==================== GLOBALS ====================
user_videos = {}
user_requests = defaultdict(list)
error_stats = defaultdict(int)
MAX_REQUESTS_PER_MINUTE = 5

# ✨ DATABASE
db = Database()


# ==================== ERROR HANDLER ====================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler"""
    logger.error("❌ Exception while handling an update:", exc_info=context.error)

    error_type = type(context.error).__name__
    error_stats[error_type] += 1

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)
    logger.error(f"Full traceback:\n{tb_string}")

    if update and isinstance(update, Update):
        try:
            error_messages = {
                "NetworkError": "🌐 Internet muammosi. Qaytadan urinib ko'ring.",
                "TimedOut": "⏱ Vaqt tugadi. Qaytadan urinib ko'ring.",
                "BadRequest": "❌ Noto'g'ri so'rov. Qaytadan boshlang: /start",
                "Forbidden": "🚫 Bot bloklangan. Blokdan chiqaring.",
                "RetryAfter": "⏳ Juda tez! Biroz kuting.",
                "TelegramError": "📡 Telegram xatoligi. Biroz kutib qaytadan urinib ko'ring.",
            }

            user_message = error_messages.get(
                error_type,
                "❌ Kutilmagan xatolik yuz berdi!\n\n"
                "Qaytadan urinib ko'ring yoki /start bosing.\n\n"
                "Muammo davom etsa: @d_jumanazarov"
            )

            if update.effective_message:
                await update.effective_message.reply_text(user_message)
            elif update.callback_query:
                await update.callback_query.answer(user_message, show_alert=True)

        except Exception as e:
            logger.error(f"Error handler failed to send message: {e}")


# ==================== HELPERS ====================
def check_rate_limit(user_id):
    """Rate limiting"""
    now = time.time()
    user_requests[user_id] = [t for t in user_requests[user_id] if now - t < 60]

    if len(user_requests[user_id]) >= MAX_REQUESTS_PER_MINUTE:
        return False

    user_requests[user_id].append(now)
    return True


def cleanup_old_files():
    """Eski fayllarni tozalash"""
    try:
        if not os.path.exists('downloads'):
            return

        now = time.time()
        deleted = 0

        for filename in os.listdir('downloads'):
            filepath = os.path.join('downloads', filename)
            if os.path.isfile(filepath) and now - os.path.getmtime(filepath) > 1800:
                os.remove(filepath)
                deleted += 1

        if deleted > 0:
            logger.info(f"🧹 Cleaned up {deleted} old files")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


def detect_platform_and_type(url):
    """Platform va video turini aniqlash"""
    try:
        url_lower = url.lower()

        if 'instagram.com/reel' in url_lower or 'instagr.am/reel' in url_lower:
            return 'instagram', 'shorts', True
        elif 'instagram.com' in url_lower or 'instagr.am' in url_lower:
            return 'instagram', 'post', False
        elif 'youtube.com/shorts' in url_lower:
            return 'youtube', 'shorts', True
        elif 'youtu.be/' in url_lower:
            return 'youtube', 'short_link', True
        elif 'youtube.com/watch' in url_lower:
            return 'youtube', 'video', False
        elif 'tiktok.com' in url_lower:
            return 'tiktok', 'shorts', True
        else:
            return 'other', 'unknown', False
    except Exception as e:
        logger.error(f"Platform detection error: {e}")
        return 'other', 'unknown', False


# ==================== COMMANDS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    try:
        user_id = update.effective_user.id
        username = update.effective_user.username or "User"
        first_name = update.effective_user.first_name or "User"

        logger.info(f"👤 User {user_id} (@{username}) started bot")

        # ✨ DATABASE'GA QO'SHISH
        db.add_user(user_id, username, first_name)

        await update.message.reply_text(
            "🎬 *Salom! Shorts Video Downloader Botga xush kelibsiz!*\n\n"
            "📌 *Qanday ishlaydi:*\n\n"
            "1️⃣ Faqat Shorts video linkini yuboring\n"
            "2️⃣ Sifatni tanlang\n"
            "3️⃣ Videoni yuklab oling!\n\n"
            "✅ *Qo'llab-quvvatlanadigan formatlar:*\n"
            "• YouTube Shorts\n"
            "• Instagram Reels\n"
            "• TikTok videolar\n\n"
            "⚠️ *Muhim:* Faqat qisqa videolar (Shorts/Reels) yuklanadi!\n"
            "Oddiy uzun YouTube videolar qabul qilinmaydi.\n\n"
            "📊 Yordam: /help",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"/start error: {e}")
        await update.message.reply_text("❌ Xatolik. Qaytadan urinib ko'ring.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    try:
        await update.message.reply_text(
            "📖 *Yordam*\n\n"
            "🎬 *Qabul qilinadigan linklar:*\n\n"
            "✅ YouTube Shorts:\n"
            "   `youtube.com/shorts/...`\n"
            "   `youtu.be/...` (qisqa link)\n\n"
            "✅ Instagram Reels:\n"
            "   `instagram.com/reel/...`\n\n"
            "✅ TikTok:\n"
            "   `tiktok.com/@.../video/...`\n\n"
            "❌ *Qabul qilinmaydi:*\n"
            "   Oddiy YouTube videolar\n"
            "   Uzun formatli videolar\n\n"
            "💡 Bot faqat 50MB gacha videolarni yuklay oladi.\n\n"
            "⏱ Limit: 5 video/daqiqa per user\n\n"
            "📊 *Komandalar:*\n"
            "/start - Boshlash\n"
            "/help - Yordam\n"
            "/mystat - Sizning statistikangiz\n\n"
            "👨‍💻 Murojaat: @d_jumanazarov",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"/help error: {e}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats command - admin only"""
    try:
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ Bu komanda faqat admin uchun!")
            return

        # ✨ LIGHT STATISTIKA
        total_users = db.get_total_users()
        total_downloads = db.get_total_downloads()
        platform_stats = db.get_platform_stats()
        quality_stats = db.get_quality_stats()

        stats_text = (
            f"📊 *Bot Statistikasi*\n\n"
            f"👥 Jami foydalanuvchilar: {total_users}\n"
            f"⬇️ Jami yuklanishlar: {total_downloads}\n"
            f"📹 Hozir yuklanayotgan: {len(user_videos)}\n\n"
        )

        # Platform statistikasi
        if platform_stats:
            stats_text += "🌐 *Platformalar:*\n"
            platform_emojis = {
                'youtube': '▶️ YouTube',
                'instagram': '📸 Instagram',
                'tiktok': '🎵 TikTok'
            }
            for row in platform_stats:
                emoji = platform_emojis.get(row['platform'], f"🎬 {row['platform'].title()}")
                stats_text += f"{emoji}: {row['downloads']}\n"
            stats_text += "\n"

        # Sifat statistikasi
        if quality_stats:
            stats_text += "🎬 *Top 5 Sifatlar:*\n"
            for row in quality_stats[:5]:
                stats_text += f"• {row['quality']}: {row['count']}\n"
            stats_text += "\n"

        stats_text += f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        await update.message.reply_text(stats_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"/stats error: {e}")
        await update.message.reply_text("❌ Xatolik yuz berdi")


async def mystat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User o'z statistikasini ko'radi"""
    try:
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name

        # User ma'lumotini olish
        cursor = db.conn.cursor()
        cursor.execute('''
            SELECT first_seen, last_seen FROM users WHERE user_id = ?
        ''', (user_id,))

        user_data = cursor.fetchone()

        if not user_data:
            await update.message.reply_text("❌ Ma'lumot topilmadi. /start bosing!")
            return

        first_seen = datetime.fromisoformat(user_data['first_seen'])
        days_active = (datetime.now() - first_seen).days

        total_users = db.get_total_users()
        total_downloads = db.get_total_downloads()

        mystat_text = (
            f"📊 *Sizning Statistikangiz*\n\n"
            f"👤 User: {username}\n"
            f"🆔 ID: `{user_id}`\n"
            f"📅 Qo'shilgan: {first_seen.strftime('%Y-%m-%d')}\n"
            f"⏰ Faollik: {days_active} kun\n\n"
            f"🌐 *Bot Statistikasi:*\n"
            f"👥 Jami userlar: {total_users}\n"
            f"⬇️ Jami yuklanishlar: {total_downloads}"
        )

        await update.message.reply_text(mystat_text, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"/mystat error: {e}")
        await update.message.reply_text("❌ Xatolik yuz berdi")


async def errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Errors command - admin only"""
    try:
        user_id = update.effective_user.id

        logger.info(f"🔍 /errors called by {user_id}")

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ Bu komanda faqat admin uchun!")
            return

        if not error_stats:
            await update.message.reply_text("✅ Hech qanday xatolik yo'q!")
            return

        stats_text = "📊 *Xatolik Statistikasi:*\n\n"

        for error_type, count in sorted(error_stats.items(), key=lambda x: x[1], reverse=True):
            stats_text += f"• {error_type}: {count}x\n"

        await update.message.reply_text(stats_text, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"/errors error: {e}")
        await update.message.reply_text("❌ Xatolik yuz berdi")


# ==================== MESSAGE HANDLERS ====================
async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Link qabul qilish"""
    try:
        url = update.message.text.strip()
        user_id = update.effective_user.id

        logger.info(f"📥 User {user_id} sent URL: {url[:50]}...")

        if not check_rate_limit(user_id):
            await update.message.reply_text(
                "⏱ *Juda tez yuborilmoqda!*\n\n"
                "Iltimos, 1 daqiqa kuting.\n"
                "Limit: 5 video/daqiqa",
                parse_mode='Markdown'
            )
            return

        platform, video_type, is_shorts = detect_platform_and_type(url)

        logger.info(f"📊 Detected: {platform.upper()} - {video_type}")

        if not is_shorts:
            platform_messages = {
                'youtube': (
                    "❌ *Kechirasiz, faqat Shorts videolar yuklanadi!*\n\n"
                    "Siz oddiy YouTube video linkini yubordingiz.\n\n"
                    "✅ *To'g'ri link:*\n"
                    "`youtube.com/shorts/XXXXX`\n\n"
                    "💡 YouTube Shorts videolarini yuboring!"
                ),
                'instagram': (
                    "❌ *Kechirasiz, faqat Reels yuklanadi!*\n\n"
                    "Siz oddiy Instagram post linkini yubordingiz.\n\n"
                    "✅ *To'g'ri link:*\n"
                    "`instagram.com/reel/XXXXX`\n\n"
                    "💡 Instagram Reels videolarini yuboring!"
                ),
                'other': (
                    "❌ *Kechirasiz, bu link qo'llab-quvvatlanmaydi!*\n\n"
                    "✅ *Qo'llab-quvvatlanadigan platformalar:*\n"
                    "• YouTube Shorts\n"
                    "• Instagram Reels\n"
                    "• TikTok\n\n"
                    "Yordam: /help"
                )
            }

            message = platform_messages.get(platform, platform_messages['other'])
            await update.message.reply_text(message, parse_mode='Markdown')
            return

        user_videos[user_id] = {'url': url, 'platform': platform}

        keyboard = [
            [
                InlineKeyboardButton("📱 144p", callback_data="quality_144"),
                InlineKeyboardButton("📺 360p", callback_data="quality_360"),
            ],
            [
                InlineKeyboardButton("🎬 480p", callback_data="quality_480"),
                InlineKeyboardButton("🔥 720p", callback_data="quality_720"),
            ],
            [
                InlineKeyboardButton("💎 1080p (Full HD)", callback_data="quality_1080"),
            ],
            [
                InlineKeyboardButton("⭐ Eng yaxshi", callback_data="quality_best"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        platform_emoji = {
            'instagram': '📸 Instagram Reels',
            'youtube': '▶️ YouTube Shorts',
            'tiktok': '🎵 TikTok',
            'other': '🎬 Shorts'
        }

        await update.message.reply_text(
            f"✅ *{platform_emoji.get(platform, '🎬 Shorts')} aniqlandi!*\n\n"
            f"📊 *Qaysi sifatda yuklab olmoqchisiz?*\n\n"
            "💡 Past sifat = Tezroq\n"
            "⭐ Yuqori sifat = Sifatli",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"receive_link error: {e}", exc_info=True)
        await update.message.reply_text("❌ Xatolik. Qaytadan link yuboring.")


async def quality_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quality selection handler"""
    query = update.callback_query

    try:
        await query.answer()

        user_id = query.from_user.id
        user_data = user_videos.get(user_id)

        if not user_data:
            await query.edit_message_text("❌ Link topilmadi. Qaytadan yuboring.")
            return

        url = user_data['url']
        platform = user_data['platform']
        quality = query.data.split('_')[1]

        # Quality mappings
        if platform == 'instagram':
            quality_map = {
                '144': {'format': 'worst', 'target': 256, 'name': '144p'},
                '360': {'format': 'bestvideo[height<=640]+bestaudio/best[height<=640]', 'target': 640, 'name': '360p'},
                '480': {'format': 'bestvideo[height<=854]+bestaudio/best[height<=854]', 'target': 854, 'name': '480p'},
                '720': {'format': 'bestvideo[height<=1280]+bestaudio/best[height<=1280]', 'target': 1280,
                        'name': '720p'},
                '1080': {'format': 'bestvideo[height<=1920]+bestaudio/best[height<=1920]', 'target': 1920,
                         'name': '1080p (Full HD)'},
                'best': {'format': 'best', 'target': 9999, 'name': 'Eng yaxshi'}
            }
        else:
            quality_map = {
                '144': {'format': 'bestvideo[height<=256]+bestaudio/best[height<=256]/worst', 'target': 256,
                        'name': '144p'},
                '360': {'format': 'bestvideo[height<=640]+bestaudio/best[height<=640]', 'target': 640, 'name': '360p'},
                '480': {'format': 'bestvideo[height<=854]+bestaudio/best[height<=854]', 'target': 854, 'name': '480p'},
                '720': {'format': 'bestvideo[height<=1280]+bestaudio/best[height<=1280]', 'target': 1280,
                        'name': '720p'},
                '1080': {'format': 'bestvideo[height<=1920]+bestaudio/best[height<=1920]', 'target': 1920,
                         'name': '1080p (Full HD)'},
                'best': {'format': 'bestvideo+bestaudio/best', 'target': 9999, 'name': 'Eng yaxshi'}
            }

        quality_config = quality_map.get(quality, quality_map['best'])
        format_choice = quality_config['format']
        target_height = quality_config['target']
        quality_name = quality_config['name']

        await query.edit_message_text(f"⏳ {quality_name} yuklanmoqda...")

        timestamp = int(time.time())
        output_template = f'downloads/{user_id}_{timestamp}_%(id)s.%(ext)s'

        ydl_opts = {
            'format': format_choice,
            'outtmpl': output_template,

            # ✨ YouTube bot detection bypass
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'android', 'web'],
                    'skip': ['hls', 'dash'],
                    'player_skip': ['webpage', 'configs'],
                }
            },

            # ✨ Better headers
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

            # ✨ Additional bypass options
            'nocheckcertificate': True,
            'age_limit': None,
        }

        os.makedirs('downloads', exist_ok=True)
        loop = asyncio.get_event_loop()

        def download():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    video_path = ydl.prepare_filename(info)
                    title = info.get('title', 'Video')
                    actual_height = info.get('height', 0)
                    actual_width = info.get('width', 0)
                    duration = info.get('duration', 0)
                    return video_path, title, actual_height, actual_width, duration
            except Exception as e:
                logger.error(f"Download error: {e}")
                raise

        # Retry mechanism
        max_retries = 3
        retry_count = 0
        video_path = None

        while retry_count < max_retries:
            try:
                video_path, title, actual_height, actual_width, duration = await loop.run_in_executor(None, download)
                break
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise
                logger.warning(f"Download failed, retry {retry_count}/{max_retries}")
                await asyncio.sleep(2)
                await query.edit_message_text(f"⏳ Qayta urinish {retry_count}/{max_retries}...")

        # Duration check
        if duration and duration > 180:
            await query.edit_message_text(
                "❌ *Bu video juda uzun!*\n\n"
                f"Video davomiyligi: {duration // 60} daqiqa {duration % 60} soniya\n\n"
                "Bot faqat qisqa videolar (Shorts/Reels) uchun.\n"
                "💡 3 daqiqadan qisqa videolarni yuboring!",
                parse_mode='Markdown'
            )
            if os.path.exists(video_path):
                os.remove(video_path)
            if user_id in user_videos:
                del user_videos[user_id]
            return

        if not os.path.exists(video_path):
            raise FileNotFoundError("Video fayl topilmadi")

        file_size = os.path.getsize(video_path)
        file_size_mb = file_size / (1024 * 1024)

        is_vertical = actual_height > actual_width
        video_type = "Vertikal" if is_vertical else "Gorizontal"

        logger.info(
            f"📊 {platform.upper()} | {video_type} | {actual_width}x{actual_height} | {file_size_mb:.1f}MB | {duration}s")

        # Telegram file size limit
        if file_size > 50 * 1024 * 1024:
            await query.edit_message_text(
                f"❌ *Video juda katta!*\n\n"
                f"Hajm: {file_size_mb:.1f} MB\n"
                f"Telegram limiti: 50 MB\n\n"
                f"💡 Pastroq sifat tanlang!",
                parse_mode='Markdown'
            )
            os.remove(video_path)
            if user_id in user_videos:
                del user_videos[user_id]
            return

        quality_info = ""
        if quality != 'best' and actual_height < target_height:
            quality_info = f"\n📌 Asl sifat: {actual_height}p"

        await query.edit_message_text(f"📤 Telegram'ga yuborilmoqda... ({file_size_mb:.1f} MB)")

        resolution_text = f"{actual_width}x{actual_height}"

        # Send video with retry
        max_send_retries = 2
        send_retry = 0

        while send_retry < max_send_retries:
            try:
                with open(video_path, 'rb') as video:
                    await context.bot.send_video(
                        chat_id=query.message.chat_id,
                        video=video,
                        caption=(
                            f"✅ *{title[:70]}*\n\n"
                            f"📊 So'ralgan: {quality_name}\n"
                            f"📐 Yuborildi: {resolution_text}\n"
                            f"🗂 Hajmi: {file_size_mb:.1f} MB{quality_info}\n\n"
                            f"❗️ [Dilshod](https://t.me/d_jumanazarov) ga rahmat deb qo'yish esdan chiqmasin😁"
                        ),
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120,
                        parse_mode='Markdown'
                    )
                break

            except Exception as send_error:
                send_retry += 1
                if send_retry >= max_send_retries:
                    raise
                logger.warning(f"Send video failed, retry {send_retry}/{max_send_retries}")
                await asyncio.sleep(3)

        await query.delete_message()

        # ✨ STATISTIKANI YANGILASH
        db.increment_platform(platform)
        db.increment_quality(quality_name)

        # Cleanup
        if os.path.exists(video_path):
            os.remove(video_path)
            logger.info(f"🗑 Deleted file: {video_path}")

        if user_id in user_videos:
            del user_videos[user_id]

        logger.info(f"✅ {quality_name} → {resolution_text} | {file_size_mb:.1f}MB")

    except asyncio.TimeoutError:
        logger.error("Timeout error in quality_selected")
        try:
            await query.edit_message_text(
                "❌ *Vaqt tugadi!*\n\n"
                "Video yuklanmadi yoki yuborilmadi.\n\n"
                "💡 Qaytadan urinib ko'ring",
                parse_mode='Markdown'
            )
        except:
            pass
        if user_id in user_videos:
            del user_videos[user_id]

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        try:
            await query.edit_message_text("❌ *Video fayl topilmadi!*\n\nQaytadan urinib ko'ring.")
        except:
            pass
        if user_id in user_videos:
            del user_videos[user_id]

    except Exception as e:
        logger.error(f"❌ quality_selected error: {e}", exc_info=True)
        error_msg = str(e)

        try:
            if "Requested format is not available" in error_msg:
                await query.edit_message_text("❌ *Bu sifat mavjud emas!*\n\n💡 Boshqa sifatni tanlang")
            elif "Video is unavailable" in error_msg or "Private video" in error_msg:
                await query.edit_message_text("❌ *Video mavjud emas yoki private!*\n\nBoshqa video linkini yuboring.")
            elif "HTTP Error 429" in error_msg:
                await query.edit_message_text("⏱ *Juda ko'p so'rov!*\n\n5 daqiqa kutib qaytadan urinib ko'ring.")
            else:
                await query.edit_message_text(
                    f"❌ *Xatolik yuz berdi!*\n\n"
                    f"Xatolik: {error_msg[:150]}\n\n"
                    f"Qaytadan urinib ko'ring yoki @d_jumanazarov ga murojaat qiling."
                )
        except:
            pass

        if user_id in user_videos:
            del user_videos[user_id]

        # Cleanup
        try:
            if 'video_path' in locals() and video_path and os.path.exists(video_path):
                os.remove(video_path)
        except:
            pass


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Echo handler"""
    try:
        await update.message.reply_text(
            "❓ *Shorts video linkini yuboring!*\n\n"
            "✅ Qabul qilinadigan formatlar:\n"
            "• YouTube Shorts\n"
            "• Instagram Reels\n"
            "• TikTok\n\n"
            "Yordam: /help",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"echo error: {e}")


# ==================== SHUTDOWN ====================
async def shutdown(application):
    """Graceful shutdown"""
    try:
        logger.info("🛑 Bot to'xtatilmoqda...")
        cleanup_old_files()

        if error_stats:
            logger.info("📊 Final error stats:")
            for error_type, count in error_stats.items():
                logger.info(f"  - {error_type}: {count}")

        # Database yopish
        db.close()

        logger.info("✅ Bot to'xtatildi")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# ==================== MAIN ====================
def main():
    """Main function"""
    try:
        logger.info("🚀 Initializing bot...")

        # ✨ HEALTH CHECK SERVER
        health_port = int(os.getenv('PORT', 8080))
        health_thread = threading.Thread(
            target=start_health_server,
            args=(health_port,),
            daemon=True
        )
        health_thread.start()
        logger.info(f"✅ Health check server started on port {health_port}")

        # Cleanup old files
        cleanup_old_files()

        # Build application
        app = Application.builder().token(BOT_TOKEN).build()

        # Global error handler
        app.add_error_handler(error_handler)
        logger.info("✅ Error handler registered")

        # Command handlers
        app.add_handler(CommandHandler("start", start))
        logger.info("✅ /start handler registered")

        app.add_handler(CommandHandler("help", help_command))
        logger.info("✅ /help handler registered")

        app.add_handler(CommandHandler("stats", stats_command))
        logger.info("✅ /stats handler registered")

        app.add_handler(CommandHandler("mystat", mystat_command))
        logger.info("✅ /mystat handler registered")

        app.add_handler(CommandHandler("errors", errors_command))
        logger.info("✅ /errors handler registered")

        # Message handlers
        app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^https?://'), receive_link))
        logger.info("✅ Link handler registered")

        app.add_handler(CallbackQueryHandler(quality_selected, pattern='^quality_'))
        logger.info("✅ Quality handler registered")

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
        logger.info("✅ Echo handler registered")

        # Shutdown handler
        app.post_shutdown = shutdown

        # Start bot
        logger.info("🤖 Bot ishga tushdi!")
        logger.info("✅ Error handling enabled")
        logger.info("✅ Auto-retry enabled")
        logger.info("✅ Health check enabled")

        # Run polling
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )

    except Exception as e:
        logger.critical(f"❌ CRITICAL ERROR in main(): {e}", exc_info=True)
        raise


if __name__ == '__main__':
    main()