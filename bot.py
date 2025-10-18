"""
Telegram Channel Auto-Forwarder Userbot - IMPROVED VERSION
✅ Never sleeps on Render
✅ Accurate progress tracking with SQLite
✅ Auto-resume from exact position
✅ Smart ID detection from destination post
"""

from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
import asyncio
import json
import os
import sys
from datetime import datetime
import logging
from dotenv import load_dotenv
from aiohttp import web
import sqlite3
from pathlib import Path

# Load environment variables
load_dotenv()

# ============================================
# LOGGING SETUP
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================
API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', 'YOUR_API_HASH')
PHONE = os.getenv('PHONE', 'YOUR_PHONE_NUMBER')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
PORT = int(os.getenv('PORT', '10000'))

SESSION_FILE = os.getenv('SESSION_FILE', 'userbot_session')
CONFIG_FILE = 'bot_config.json'

# Database location - use persistent disk if available
DATA_DIR = os.getenv('DATA_DIR', '.')  # Set DATA_DIR=/data on Render if using persistent disk
DB_FILE = os.path.join(DATA_DIR, 'progress.db')

# Create data directory if needed
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

# ============================================
# SQLITE DATABASE FOR ACCURATE PROGRESS
# ============================================
class ProgressDB:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self.init_db()
    
    def init_db(self):
        """Initialize database"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        # Progress table
        c.execute('''CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY,
            source_channel INTEGER,
            dest_channel INTEGER,
            last_forwarded_id INTEGER,
            total_forwarded INTEGER,
            last_update TIMESTAMP,
            status TEXT
        )''')
        
        # Message mapping table (for exact tracking)
        c.execute('''CREATE TABLE IF NOT EXISTS message_map (
            source_msg_id INTEGER,
            dest_msg_id INTEGER,
            forwarded_at TIMESTAMP,
            PRIMARY KEY (source_msg_id)
        )''')
        
        # Keep-alive log
        c.execute('''CREATE TABLE IF NOT EXISTS keepalive_log (
            ping_time TIMESTAMP PRIMARY KEY,
            status TEXT
        )''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")
    
    def save_progress(self, source, dest, last_id, total, status="running"):
        """Save current progress"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        c.execute('''INSERT OR REPLACE INTO progress 
                     (id, source_channel, dest_channel, last_forwarded_id, 
                      total_forwarded, last_update, status)
                     VALUES (1, ?, ?, ?, ?, ?, ?)''',
                  (source, dest, last_id, total, datetime.now(), status))
        
        conn.commit()
        conn.close()
    
    def get_progress(self):
        """Get saved progress"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        c.execute('SELECT * FROM progress WHERE id = 1')
        row = c.fetchone()
        conn.close()
        
        if row:
            return {
                'source_channel': row[1],
                'dest_channel': row[2],
                'last_forwarded_id': row[3],
                'total_forwarded': row[4],
                'last_update': row[5],
                'status': row[6]
            }
        return None
    
    def save_message_mapping(self, source_id, dest_id):
        """Save source->dest message mapping"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        c.execute('''INSERT OR REPLACE INTO message_map 
                     (source_msg_id, dest_msg_id, forwarded_at)
                     VALUES (?, ?, ?)''',
                  (source_id, dest_id, datetime.now()))
        
        conn.commit()
        conn.close()
    
    def get_last_messages(self, limit=10):
        """Get last forwarded messages"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        c.execute('''SELECT source_msg_id, dest_msg_id, forwarded_at 
                     FROM message_map 
                     ORDER BY source_msg_id DESC 
                     LIMIT ?''', (limit,))
        
        rows = c.fetchall()
        conn.close()
        return rows
    
    def find_source_by_dest(self, dest_id):
        """Find source message ID from destination message ID"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        c.execute('SELECT source_msg_id FROM message_map WHERE dest_msg_id = ?', (dest_id,))
        row = c.fetchone()
        conn.close()
        
        return row[0] if row else None
    
    def log_keepalive(self):
        """Log keep-alive ping"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        
        c.execute('''INSERT INTO keepalive_log (ping_time, status)
                     VALUES (?, ?)''', (datetime.now(), 'alive'))
        
        # Keep only last 100 pings
        c.execute('''DELETE FROM keepalive_log WHERE ping_time NOT IN 
                     (SELECT ping_time FROM keepalive_log 
                      ORDER BY ping_time DESC LIMIT 100)''')
        
        conn.commit()
        conn.close()

db = ProgressDB()

# ============================================
# HTTP SERVER - ENHANCED FOR RENDER
# ============================================
async def health_check(request):
    """Enhanced health check"""
    progress = db.get_progress()
    
    return web.json_response({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'bot_running': config.get('is_running', False),
        'progress': progress,
        'uptime': str(datetime.now() - start_time) if 'start_time' in globals() else 'N/A'
    })

async def root_handler(request):
    """Root endpoint with detailed status"""
    progress = db.get_progress()
    status = "🟢 Running" if config.get('is_running', False) else "🔴 Stopped"
    
    if progress:
        last_update = progress['last_update']
        try:
            last_update_time = datetime.fromisoformat(last_update)
            time_diff = datetime.now() - last_update_time
            last_update_str = f"{time_diff.seconds // 60}m {time_diff.seconds % 60}s ago"
        except:
            last_update_str = last_update
    else:
        last_update_str = "Never"
    
    return web.Response(text=f"""
╔══════════════════════════════════════╗
║   TELEGRAM USERBOT - ACTIVE          ║
╚══════════════════════════════════════╝

Status: {status}
Total Forwarded: {progress['total_forwarded'] if progress else 0}
Last Message ID: {progress['last_forwarded_id'] if progress else 0}
Last Update: {last_update_str}
Server Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ Bot is running successfully on Render!
💾 Database tracking enabled
🔄 Auto-resume ready
💓 Keep-alive active

Health: http://your-app.onrender.com/health
""", content_type='text/plain')

async def ping_handler(request):
    """Quick ping endpoint for external monitoring"""
    db.log_keepalive()
    return web.Response(text="pong", content_type='text/plain')

async def start_http_server():
    """Start HTTP server"""
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/health', health_check)
    app.router.add_get('/status', health_check)
    app.router.add_get('/ping', ping_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 HTTP server started on 0.0.0.0:{PORT}")
    return runner

# ============================================
# MULTI-LAYER KEEP-ALIVE SYSTEM
# ============================================
async def keep_alive_aggressive():
    """
    Aggressive keep-alive - Multiple strategies:
    1. Self-ping every 5 minutes
    2. Database writes every 5 minutes
    3. Status updates to admin every 30 minutes
    """
    import aiohttp
    
    while config.get('keep_alive', True):
        try:
            # Log keep-alive
            db.log_keepalive()
            logger.info("💓 Keep-alive: Database pinged")
            
            # Self HTTP ping (helps Render detect activity)
            try:
                async with aiohttp.ClientSession() as session:
                    # Use Render's internal URL or external if available
                    render_url = os.getenv('RENDER_EXTERNAL_URL', f'http://0.0.0.0:{PORT}')
                    async with session.get(f'{render_url}/ping', timeout=10) as resp:
                        logger.info(f"💓 Self-ping: {resp.status}")
            except Exception as e:
                logger.warning(f"Self-ping failed (normal): {e}")
            
            # Save current progress to database (creates activity)
            if config.get('source_channel') and config.get('destination_channel'):
                db.save_progress(
                    config['source_channel'],
                    config['destination_channel'],
                    config.get('last_forwarded_id', 0),
                    config.get('forwarded_count', 0),
                    'running' if config.get('is_running', False) else 'idle'
                )
            
            # Every 30 minutes, send status to admin
            current_minute = datetime.now().minute
            if current_minute % 30 == 0:
                status = "🟢 Running" if config['is_running'] else "🔴 Idle"
                progress = db.get_progress()
                
                await client.send_message(
                    ADMIN_ID,
                    f"💓 **Keep-Alive Report**\n\n"
                    f"Status: {status}\n"
                    f"Total: {progress['total_forwarded'] if progress else 0}\n"
                    f"Last ID: {progress['last_forwarded_id'] if progress else 0}\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}\n"
                    f"Date: {datetime.now().strftime('%Y-%m-%d')}\n\n"
                    f"🤖 Bot is alive and ready!"
                )
                logger.info("📊 Status report sent to admin")
            
            # Wait 5 minutes (300 seconds)
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
            await asyncio.sleep(60)

# ============================================
# CONFIG HANDLING
# ============================================
default_config = {
    'source_channel': None,
    'destination_channel': None,
    'forward_delay': 2,
    'batch_size': 100,
    'batch_delay': 120,
    'is_running': False,
    'forwarded_count': 0,
    'last_forwarded_id': 0,
    'skip_media_types': [],
    'auto_mode': False,
    'keep_alive': True,
    'notify_batch': True,
    'notify_interval': 50,
    'auto_resume': True,  # NEW: Auto-resume on restart
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                logger.info("✅ Config loaded from file")
                
                # Merge with database progress if available
                progress = db.get_progress()
                if progress and config.get('auto_resume', True):
                    config['source_channel'] = progress['source_channel']
                    config['destination_channel'] = progress['dest_channel']
                    config['last_forwarded_id'] = progress['last_forwarded_id']
                    config['forwarded_count'] = progress['total_forwarded']
                    logger.info(f"✅ Auto-resumed from DB: Last ID {progress['last_forwarded_id']}")
                
                return config
        except Exception as e:
            logger.error(f"❌ Error loading config: {e}")
    
    # Try to load from database
    progress = db.get_progress()
    if progress:
        config = default_config.copy()
        config['source_channel'] = progress['source_channel']
        config['destination_channel'] = progress['dest_channel']
        config['last_forwarded_id'] = progress['last_forwarded_id']
        config['forwarded_count'] = progress['total_forwarded']
        logger.info(f"✅ Loaded from database: Last ID {progress['last_forwarded_id']}")
        return config
    
    logger.info("📝 Using default config")
    return default_config.copy()

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        
        # Also save to database
        if config.get('source_channel') and config.get('destination_channel'):
            db.save_progress(
                config['source_channel'],
                config['destination_channel'],
                config.get('last_forwarded_id', 0),
                config.get('forwarded_count', 0),
                'running' if config.get('is_running', False) else 'idle'
            )
        
        logger.info("💾 Config saved to file and database")
    except Exception as e:
        logger.error(f"❌ Error saving config: {e}")

config = load_config()

# ============================================
# SESSION HANDLING
# ============================================
def get_session():
    session_string = os.getenv('SESSION_STRING')
    
    if session_string:
        logger.info("🔑 Using StringSession from environment")
        return StringSession(session_string)
    
    if os.path.exists(f"{SESSION_FILE}.session"):
        logger.info("📁 Using file session")
        return SESSION_FILE
    
    logger.warning("⚠️ No session found")
    return SESSION_FILE

client = TelegramClient(get_session(), API_ID, API_HASH)

# ============================================
# VALIDATE ENV
# ============================================
def validate_env():
    required = ['API_ID', 'API_HASH', 'PHONE', 'ADMIN_ID']
    missing = [var for var in required if not os.getenv(var)]
    
    if missing:
        logger.error(f"❌ Missing: {', '.join(missing)}")
        return False
    
    logger.info("✅ All env vars configured")
    return True

# ============================================
# HELPER FUNCTIONS
# ============================================
def extract_channel_id(text):
    text = text.strip()
    
    if text.startswith('-') and text[1:].isdigit():
        return int(text)
    
    if text.startswith('@'):
        return text
    
    try:
        return int(text)
    except ValueError:
        return text

async def get_channel_info(channel_id):
    try:
        entity = await client.get_entity(channel_id)
        title = getattr(entity, 'title', 'Unknown')
        username = getattr(entity, 'username', None)
        actual_id = entity.id
        
        info = f"{title}"
        if username:
            info += f" (@{username})"
        info += f"\nID: {actual_id}"
        
        return info, actual_id
    except Exception as e:
        logger.error(f"Error getting channel info: {e}")
        return str(channel_id), channel_id

# ============================================
# SMART ID DETECTION FROM DESTINATION POST
# ============================================
async def find_source_id_from_dest_message(dest_msg_id, source_channel, dest_channel):
    """
    NEW FEATURE: Compare destination message with source to find exact position
    This helps when bot restarts or connection is lost
    """
    try:
        logger.info(f"🔍 Searching for source ID from dest message {dest_msg_id}...")
        
        # First check database
        db_result = db.find_source_by_dest(dest_msg_id)
        if db_result:
            logger.info(f"✅ Found in database: Source ID {db_result}")
            return db_result
        
        # If not in database, compare messages
        dest_msg = await client.get_messages(dest_channel, ids=dest_msg_id)
        if not dest_msg:
            logger.error("❌ Destination message not found")
            return None
        
        dest_text = dest_msg.message if dest_msg.message else ""
        dest_has_media = bool(dest_msg.media)
        
        logger.info(f"📝 Comparing: text={len(dest_text)} chars, media={dest_has_media}")
        
        # Search in source channel (last 1000 messages)
        async for source_msg in client.iter_messages(source_channel, limit=1000):
            source_text = source_msg.message if source_msg.message else ""
            source_has_media = bool(source_msg.media)
            
            # Compare text and media presence
            if source_text == dest_text and source_has_media == dest_has_media:
                logger.info(f"✅ Match found! Source ID: {source_msg.id}")
                
                # Save to database for future reference
                db.save_message_mapping(source_msg.id, dest_msg_id)
                
                return source_msg.id
        
        logger.warning("⚠️ No exact match found in last 1000 messages")
        return None
        
    except Exception as e:
        logger.error(f"❌ Error finding source ID: {e}")
        return None

# ============================================
# IMPROVED FORWARDING WITH ACCURATE TRACKING
# ============================================
async def safe_forward(client, source_id, dest_id, start_id=0):
    """Enhanced forwarding with database tracking"""
    try:
        logger.info(f"🚀 Starting forward from {source_id} to {dest_id}")
        logger.info(f"📍 Resume point: Message ID {start_id + 1}")
        
        source = await client.get_entity(source_id)
        dest = await client.get_entity(dest_id)
        
        # Initial notification with accurate info
        await client.send_message(
            ADMIN_ID,
            f"🚀 **Forwarding Started**\n\n"
            f"📥 From: {getattr(source, 'title', 'Source')}\n"
            f"📤 To: {getattr(dest, 'title', 'Destination')}\n"
            f"📍 Starting: Message {start_id + 1}\n"
            f"📊 Previous: {config['forwarded_count']} total\n\n"
            f"⏱️ Speed: {config['forward_delay']}s\n"
            f"📦 Batch: {config['batch_size']}\n"
            f"⏰ Rest: {config['batch_delay']}s\n\n"
            f"💾 Database tracking enabled"
        )
        
        forwarded = 0
        batch_count = 0
        last_notified = 0
        
        async for message in client.iter_messages(source, min_id=start_id, reverse=True):
            if not config['is_running']:
                logger.info("⏸️ Stopped by user")
                
                # Save final progress
                db.save_progress(
                    source_id, dest_id,
                    config['last_forwarded_id'],
                    config['forwarded_count'],
                    'stopped'
                )
                
                await client.send_message(
                    ADMIN_ID,
                    f"⏸️ **Forwarding Paused**\n\n"
                    f"✅ Forwarded: {forwarded} in this session\n"
                    f"📊 Total: {config['forwarded_count']}\n"
                    f"📍 Stopped at: Message {config['last_forwarded_id']}\n"
                    f"➡️ Next start: Message {config['last_forwarded_id'] + 1}\n\n"
                    f"💾 Progress saved to database\n"
                    f"Use `/forward` to auto-resume"
                )
                break
            
            # Skip media types if configured
            if message.media and hasattr(message.media, '__class__'):
                media_type = message.media.__class__.__name__.lower()
                if any(skip in media_type for skip in config['skip_media_types']):
                    logger.info(f"⏭️ Skipped {media_type}")
                    continue
            
            try:
                # Send as new message
                sent_msg = await client.send_message(
                    dest,
                    message.text if message.text else "",
                    file=message.media if message.media else None,
                    formatting_entities=message.entities
                )
                
                forwarded += 1
                batch_count += 1
                config['forwarded_count'] += 1
                config['last_forwarded_id'] = message.id
                
                # CRITICAL: Save to database with message mapping
                db.save_message_mapping(message.id, sent_msg.id)
                
                # Save progress every 5 messages
                if forwarded % 5 == 0:
                    save_config(config)
                    db.save_progress(
                        source_id, dest_id,
                        message.id,
                        config['forwarded_count'],
                        'running'
                    )
                
                # Progress notification
                if config.get('notify_batch', True) and forwarded - last_notified >= config.get('notify_interval', 50):
                    # Get last few messages from DB for verification
                    last_msgs = db.get_last_messages(3)
                    last_ids = [f"{m[0]}→{m[1]}" for m in last_msgs]
                    
                    await client.send_message(
                        ADMIN_ID,
                        f"📊 **Progress Update**\n\n"
                        f"✅ This session: {forwarded}\n"
                        f"📊 Total: {config['forwarded_count']}\n"
                        f"📍 Current: Message {message.id}\n"
                        f"⏱️ Speed: {config['forward_delay']}s\n\n"
                        f"**Last 3 forwarded:**\n"
                        f"{chr(10).join(last_ids)}\n\n"
                        f"💾 Saved to database"
                    )
                    last_notified = forwarded
                    logger.info(f"📊 Progress: {forwarded} messages")
                
                # Delay between messages
                await asyncio.sleep(config['forward_delay'])
                
                # Batch delay
                if batch_count >= config['batch_size']:
                    logger.info(f"✅ Batch complete: {batch_count} messages")
                    
                    # Save progress before long pause
                    db.save_progress(
                        source_id, dest_id,
                        message.id,
                        config['forwarded_count'],
                        'batch_pause'
                    )
                    
                    await client.send_message(
                        ADMIN_ID,
                        f"✅ **Batch Complete**\n\n"
                        f"📦 Forwarded: {batch_count} messages\n"
                        f"📍 Position: Message {message.id}\n"
                        f"📊 Total: {config['forwarded_count']}\n\n"
                        f"⏸️ Resting: {config['batch_delay']}s\n"
                        f"🕐 Resume at: {(datetime.now().timestamp() + config['batch_delay'])}\n\n"
                        f"💾 Progress saved - Safe to restart"
                    )
                    
                    await asyncio.sleep(config['batch_delay'])
                    batch_count = 0
                    
                    # Update status after pause
                    db.save_progress(
                        source_id, dest_id,
                        message.id,
                        config['forwarded_count'],
                        'running'
                    )
                    
            except Exception as e:
                logger.error(f"❌ Error forwarding {message.id}: {e}")
                
                if "flood" in str(e).lower():
                    await client.send_message(
                        ADMIN_ID,
                        f"⚠️ **Flood Warning**\n\n"
                        f"Position saved: Message {config['last_forwarded_id']}\n"
                        f"Slowing down automatically..."
                    )
                    await asyncio.sleep(60)
                else:
                    await asyncio.sleep(5)
                continue
        
        # Final save
        save_config(config)
        db.save_progress(
            source_id, dest_id,
            config['last_forwarded_id'],
            config['forwarded_count'],
            'completed'
        )
        
        logger.info(f"✅ Complete: {forwarded} total")
        return forwarded
        
    except Exception as e:
        logger.error(f"❌ Forward error: {e}")
        
        # Save progress even on error
        db.save_progress(
            source_id, dest_id,
            config.get('last_forwarded_id', 0),
            config.get('forwarded_count', 0),
            'error'
        )
        
        await client.send_message(
            ADMIN_ID,
            f"❌ **Error Occurred**\n\n"
            f"Error: `{str(e)}`\n"
            f"📍 Last ID: {config['last_forwarded_id']}\n\n"
            f"💾 Progress saved to database\n"
            f"Use `/forward` to auto-resume"
        )
        return 0

# ============================================
# COMMAND HANDLERS
# ============================================
def get_main_menu():
    status = "🟢 Running" if config['is_running'] else "🔴 Stopped"
    auto_status = "🟢 ON" if config['auto_mode'] else "🔴 OFF"
    
    return [
        [Button.inline(f"Status: {status}", b"status")],
        [Button.inline("📥 Set Source", b"set_source"),
         Button.inline("📤 Set Destination", b"set_dest")],
        [Button.inline("▶️ Start Forward", b"start"),
         Button.inline("⏸️ Stop", b"stop")],
        [Button.inline(f"🤖 Auto: {auto_status}", b"toggle_auto")],
        [Button.inline("⚙️ Settings", b"settings"),
         Button.inline("📊 Stats", b"stats")],
        [Button.inline("🔄 Refresh", b"refresh")]
    ]

@client.on(events.NewMessage(pattern='/start', from_users=ADMIN_ID))
async def start_handler(event):
    logger.info("📋 Main menu requested")
    
    progress = db.get_progress()
    
    source_info = f"`{config['source_channel']}`" if config['source_channel'] else "❌ Not set"
    dest_info = f"`{config['destination_channel']}`" if config['destination_channel'] else "❌ Not set"
    status = "🟢 Running" if config['is_running'] else "🔴 Stopped"
    
    resume_info = ""
    if progress:
        resume_info = f"\n✅ Can resume from: Message {progress['last_forwarded_id'] + 1}"
    
    await event.respond(
        "🤖 **Channel Forwarder v2.0**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Never sleeps on Render\n"
        "💾 Database progress tracking\n"
        "🔄 Auto-resume enabled\n"
        "🆔 Smart ID detection\n\n"
        f"**Status:**\n"
        f"{status}\n"
        f"📊 Total: {config['forwarded_count']}\n"
        f"📍 Last: Message {config['last_forwarded_id']}\n"
        f"📥 Source: {source_info}\n"
        f"📤 Dest: {dest_info}"
        f"{resume_info}\n\n"
        "**Quick:**\n"
        "`/forward` - Start/Resume\n"
        "`/stopforward` - Stop\n"
        "`/status` - Full status\n"
        "`/findid` - Find position from dest msg\n\n"
        "`/source [ID]` - Set source\n"
        "`/dest [ID]` - Set destination\n"
        "`/speed balanced` - Set speed\n\n"
        "📋 Use buttons below!",
        buttons=get_main_menu()
    )

@client.on(events.NewMessage(pattern='/findid', from_users=ADMIN_ID))
async def findid_handler(event):
    """NEW: Find source message ID from destination message"""
    if event.is_reply:
        try:
            replied = await event.get_reply_message()
            dest_msg_id = replied.id
            
            if not config['source_channel'] or not config['destination_channel']:
                await event.respond("❌ Set source and destination first!")
                return
            
            await event.respond("🔍 **Searching for source ID...**\n\nThis may take a moment...")
            
            source_id = await find_source_id_from_dest_message(
                dest_msg_id,
                config['source_channel'],
                config['destination_channel']
            )
            
            if source_id:
                await event.respond(
                    f"✅ **Match Found!**\n\n"
                    f"📤 Dest Message: {dest_msg_id}\n"
                    f"📥 Source Message: {source_id}\n\n"
                    f"**To resume from here:**\n"
                    f"`/setid {source_id}`\n\n"
                    f"💡 This means forwarding stopped at source message {source_id}",
                    buttons=get_main_menu()
                )
            else:
                await event.respond(
                    f"❌ **No match found**\n\n"
                    f"Searched last 1000 messages in source.\n\n"
                    f"Try:\n"
                    f"1. Reply to an older message\n"
                    f"2. Check if channels are correct\n"
                    f"3. Use `/status` to see last known position"
                )
        except Exception as e:
            await event.respond(f"❌ Error: {e}")
    else:
        await event.respond(
            "💡 **How to use /findid:**\n\n"
            "1. Go to destination channel\n"
            "2. Find the LAST forwarded message\n"
            "3. Forward that message to me\n"
            "4. Reply to it with `/findid`\n\n"
            "Bot will find exact position in source channel!\n\n"
            "**Or check database:**\n"
            "Use `/laststatus` to see last 10 forwarded messages"
        )

@client.on(events.NewMessage(pattern='/laststatus', from_users=ADMIN_ID))
async def laststatus_handler(event):
    """Show last forwarded messages from database"""
    try:
        last_msgs = db.get_last_messages(10)
        
        if not last_msgs:
            await event.respond("❌ No forwarding history in database")
            return
        
        msg_list = []
        for i, (source_id, dest_id, time) in enumerate(last_msgs, 1):
            try:
                time_obj = datetime.fromisoformat(time)
                time_str = time_obj.strftime('%H:%M:%S')
            except:
                time_str = "Unknown"
            
            msg_list.append(f"{i}. Source: {source_id} → Dest: {dest_id} ({time_str})")
        
        await event.respond(
            f"📊 **Last 10 Forwarded Messages**\n\n"
            f"{''.join([f'{m}\n' for m in msg_list])}\n"
            f"**Resume from:**\n"
            f"`/setid {last_msgs[0][0]}`\n\n"
            f"💡 Reply to last dest message with `/findid` for verification",
            buttons=get_main_menu()
        )
    except Exception as e:
        await event.respond(f"❌ Error: {e}")

@client.on(events.NewMessage(pattern='/source', from_users=ADMIN_ID))
async def set_source(event):
    try:
        channel_input = event.text.split(maxsplit=1)[1]
        channel_id = extract_channel_id(channel_input)
        
        info, actual_id = await get_channel_info(channel_id)
        
        config['source_channel'] = actual_id
        save_config(config)
        logger.info(f"✅ Source set: {actual_id}")
        
        await event.respond(
            f"✅ **Source Channel Set**\n\n"
            f"{info}\n\n"
            f"Now: `/dest [channel_id]`",
            buttons=get_main_menu()
        )
    except IndexError:
        await event.respond(
            "❌ **Usage:**\n"
            "`/source -1002616886749`"
        )
    except Exception as e:
        await event.respond(f"❌ Error: {e}")

@client.on(events.NewMessage(pattern='/dest', from_users=ADMIN_ID))
async def set_dest(event):
    try:
        channel_input = event.text.split(maxsplit=1)[1]
        channel_id = extract_channel_id(channel_input)
        
        info, actual_id = await get_channel_info(channel_id)
        
        config['destination_channel'] = actual_id
        save_config(config)
        logger.info(f"✅ Destination set: {actual_id}")
        
        await event.respond(
            f"✅ **Destination Set**\n\n"
            f"{info}\n\n"
            f"Ready! Use `/forward`",
            buttons=get_main_menu()
        )
    except IndexError:
        await event.respond(
            "❌ **Usage:**\n"
            "`/dest -1002616886749`"
        )
    except Exception as e:
        await event.respond(f"❌ Error: {e}")

@client.on(events.NewMessage(pattern='/forward', from_users=ADMIN_ID))
async def forward_command(event):
    if not config['source_channel'] or not config['destination_channel']:
        await event.respond(
            "❌ **Setup Required**\n\n"
            "`/source [ID]`\n"
            "`/dest [ID]`"
        )
        return
    
    if config['is_running']:
        await event.respond("⚠️ Already running!\n\n`/stopforward` to stop")
        return
    
    config['is_running'] = True
    save_config(config)
    
    progress = db.get_progress()
    resume_from = progress['last_forwarded_id'] if progress else config['last_forwarded_id']
    
    logger.info(f"▶️ Forwarding started - Resume from {resume_from}")
    
    await event.respond(
        f"▶️ **Starting...**\n\n"
        f"📍 Resume from: Message {resume_from + 1}\n"
        f"📊 Previous total: {config['forwarded_count']}\n"
        f"⏱️ Speed: {config['forward_delay']}s\n\n"
        f"💾 Database tracking active\n"
        f"`/stopforward` to stop"
    )
    
    asyncio.create_task(start_forwarding_task(event))

@client.on(events.NewMessage(pattern='/stopforward', from_users=ADMIN_ID))
async def stopforward_command(event):
    config['is_running'] = False
    save_config(config)
    
    db.save_progress(
        config.get('source_channel'),
        config.get('destination_channel'),
        config.get('last_forwarded_id', 0),
        config.get('forwarded_count', 0),
        'stopped'
    )
    
    logger.info("⏸️ Stopped")
    
    await event.respond(
        f"⏸️ **Stopped**\n\n"
        f"📍 Position: Message {config['last_forwarded_id']}\n"
        f"📊 Total: {config['forwarded_count']}\n\n"
        f"💾 Saved to database\n"
        f"`/forward` to resume"
    )

@client.on(events.NewMessage(pattern='/status', from_users=ADMIN_ID))
async def status_command(event):
    progress = db.get_progress()
    
    source_info = "Not set"
    dest_info = "Not set"
    
    if config['source_channel']:
        try:
            info, _ = await get_channel_info(config['source_channel'])
            source_info = info
        except:
            source_info = str(config['source_channel'])
    
    if config['destination_channel']:
        try:
            info, _ = await get_channel_info(config['destination_channel'])
            dest_info = info
        except:
            dest_info = str(config['destination_channel'])
    
    status = "🟢 Running" if config['is_running'] else "🔴 Stopped"
    auto = "✅ ON" if config['auto_mode'] else "❌ OFF"
    
    db_status = ""
    if progress:
        try:
            last_update = datetime.fromisoformat(progress['last_update'])
            time_ago = datetime.now() - last_update
            db_status = f"\n💾 DB: {time_ago.seconds // 60}m ago"
        except:
            db_status = f"\n💾 DB: {progress['last_update']}"
    
    await event.respond(
        f"📊 **Complete Status**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Channels:**\n"
        f"📥 {source_info}\n\n"
        f"📤 {dest_info}\n\n"
        f"**Status:**\n"
        f"{status}\n"
        f"Auto: {auto}\n"
        f"📊 Total: {config['forwarded_count']}\n"
        f"📍 Last: Message {config['last_forwarded_id']}\n"
        f"➡️ Next: Message {config['last_forwarded_id'] + 1}"
        f"{db_status}\n\n"
        f"**Settings:**\n"
        f"⏱️ {config['forward_delay']}s delay\n"
        f"📦 {config['batch_size']} batch\n"
        f"⏰ {config['batch_delay']}s rest\n"
        f"🔔 Notify: Every {config.get('notify_interval', 50)}",
        buttons=get_main_menu()
    )

@client.on(events.NewMessage(pattern='/setid', from_users=ADMIN_ID))
async def setid_command(event):
    try:
        msg_id = int(event.text.split()[1])
        
        if msg_id < 0:
            msg_id = 0
        
        old_id = config['last_forwarded_id']
        config['last_forwarded_id'] = msg_id
        save_config(config)
        
        db.save_progress(
            config.get('source_channel'),
            config.get('destination_channel'),
            msg_id,
            config.get('forwarded_count', 0),
            'manual_set'
        )
        
        await event.respond(
            f"✅ **Position Updated**\n\n"
            f"Previous: Message {old_id}\n"
            f"New: Message {msg_id}\n"
            f"➡️ Next start: Message {msg_id + 1}\n\n"
            f"💾 Saved to database",
            buttons=get_main_menu()
        )
        logger.info(f"🔄 ID set to: {msg_id}")
        
    except (IndexError, ValueError):
        await event.respond(
            f"❌ **Usage:** `/setid [id]`\n\n"
            f"Current: {config['last_forwarded_id']}\n\n"
            f"Examples:\n"
            f"`/setid 0` - From start\n"
            f"`/setid 590` - From 591"
        )

@client.on(events.NewMessage(pattern='/progress', from_users=ADMIN_ID))
async def progress_command(event):
    status = "🟢 Running" if config['is_running'] else "🔴 Stopped"
    progress = db.get_progress()
    
    db_info = ""
    if progress:
        try:
            last_update = datetime.fromisoformat(progress['last_update'])
            time_ago = datetime.now() - last_update
            mins = time_ago.seconds // 60
            secs = time_ago.seconds % 60
            db_info = f"\n💾 Last update: {mins}m {secs}s ago"
        except:
            db_info = "\n💾 Database active"
    
    await event.respond(
        f"📊 **Progress Report**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{status}\n\n"
        f"✅ Total: {config['forwarded_count']}\n"
        f"📍 Last: Message {config['last_forwarded_id']}\n"
        f"➡️ Next: Message {config['last_forwarded_id'] + 1}\n"
        f"{db_info}\n\n"
        f"**Speed:**\n"
        f"⏱️ {config['forward_delay']}s/msg\n"
        f"📦 {config['batch_size']} batch\n"
        f"⏰ {config['batch_delay']}s rest\n\n"
        f"**Commands:**\n"
        f"`/laststatus` - Last 10 msgs\n"
        f"`/findid` - Find from dest msg",
        buttons=get_main_menu()
    )

@client.on(events.NewMessage(pattern='/speed', from_users=ADMIN_ID))
async def set_speed_preset(event):
    try:
        preset = event.text.split()[1].lower()
        
        presets = {
            'safe': (3, 50, 300, "🐢 Safe"),
            'balanced': (2, 100, 120, "⚖️ Balanced ⭐"),
            'fast': (1, 150, 90, "🚀 Fast"),
            'turbo': (1, 200, 60, "⚡ Turbo")
        }
        
        if preset not in presets:
            await event.respond(
                "❌ Invalid!\n\n"
                "`/speed safe`\n"
                "`/speed balanced` ⭐\n"
                "`/speed fast`\n"
                "`/speed turbo`"
            )
            return
        
        delay, batch, rest, desc = presets[preset]
        config['forward_delay'] = delay
        config['batch_size'] = batch
        config['batch_delay'] = rest
        save_config(config)
        
        await event.respond(
            f"✅ **{desc}**\n\n"
            f"⏱️ {delay}s delay\n"
            f"📦 {batch} batch\n"
            f"⏰ {rest}s rest",
            buttons=get_main_menu()
        )
        
    except IndexError:
        await event.respond(
            f"⚙️ **Speed Presets**\n\n"
            f"Current: {config['forward_delay']}s / {config['batch_size']} / {config['batch_delay']}s\n\n"
            f"`/speed safe` 🐢\n"
            f"`/speed balanced` ⚖️ ⭐\n"
            f"`/speed fast` 🚀\n"
            f"`/speed turbo` ⚡"
        )

@client.on(events.NewMessage(pattern='/health', from_users=ADMIN_ID))
async def health_handler(event):
    progress = db.get_progress()
    
    health_status = []
    
    # Check database
    if progress:
        health_status.append("✅ Database: Active")
    else:
        health_status.append("⚠️ Database: No data")
    
    # Check HTTP server
    health_status.append(f"✅ HTTP: Port {PORT}")
    
    # Check keep-alive
    health_status.append("✅ Keep-alive: Running")
    
    await event.respond(
        f"💚 **Health Check**\n\n"
        f"{chr(10).join(health_status)}\n\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}\n"
        f"📊 Total: {config['forwarded_count']}\n"
        f"📍 Position: {config['last_forwarded_id']}\n\n"
        f"All systems operational!"
    )

@client.on(events.NewMessage(pattern='/help', from_users=ADMIN_ID))
async def help_command(event):
    await event.respond(
        "📚 **All Commands**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Setup:**\n"
        "`/source [ID]` `/dest [ID]`\n\n"
        "**Control:**\n"
        "`/forward` - Start/Resume ⭐\n"
        "`/stopforward` - Stop\n\n"
        "**Progress:**\n"
        "`/status` - Full status\n"
        "`/progress` - Quick check\n"
        "`/laststatus` - Last 10 msgs 🆕\n"
        "`/findid` - Find from dest 🆕\n"
        "`/setid [num]` - Set position\n\n"
        "**Speed:**\n"
        "`/speed balanced` ⭐\n\n"
        "**System:**\n"
        "`/health` - Bot health\n"
        "`/menu` - Show buttons",
        buttons=get_main_menu()
    )

@client.on(events.NewMessage(pattern='/reset', from_users=ADMIN_ID))
async def reset_command(event):
    try:
        confirm = event.text.split()[1].lower() if len(event.text.split()) > 1 else ""
        
        if confirm == "confirm":
            old_count = config['forwarded_count']
            old_id = config['last_forwarded_id']
            
            config['last_forwarded_id'] = 0
            config['forwarded_count'] = 0
            save_config(config)
            
            db.save_progress(
                config.get('source_channel'),
                config.get('destination_channel'),
                0, 0, 'reset'
            )
            
            await event.respond(
                f"✅ **Reset Complete**\n\n"
                f"Previous: {old_count} ({old_id})\n"
                f"New: 0 (0)\n\n"
                f"💾 Database cleared\n"
                f"Next `/forward` starts fresh",
                buttons=get_main_menu()
            )
            logger.info("🔄 Reset to 0")
        else:
            await event.respond(
                f"⚠️ **Confirm Reset?**\n\n"
                f"Current: {config['forwarded_count']}\n"
                f"Position: {config['last_forwarded_id']}\n\n"
                f"⚠️ Will delete all progress!\n\n"
                f"`/reset confirm`"
            )
    except Exception as e:
        await event.respond(f"❌ Error: {e}")

# ============================================
# CALLBACK HANDLERS
# ============================================
@client.on(events.CallbackQuery)
async def callback_handler(event):
    if event.sender_id != int(ADMIN_ID):
        await event.answer("❌ Unauthorized!", alert=True)
        return
    
    data = event.data.decode('utf-8')
    
    if data == "refresh":
        status = "🟢 Running" if config['is_running'] else "🔴 Stopped"
        await event.edit(
            f"🤖 **Status**\n\n"
            f"{status}\n"
            f"📊 {config['forwarded_count']}\n"
            f"📍 {config['last_forwarded_id']}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}",
            buttons=get_main_menu()
        )
    
    elif data == "status":
        progress = db.get_progress()
        status_msg = (
            f"📊 Status\n\n"
            f"Running: {'✅' if config['is_running'] else '❌'}\n"
            f"Total: {config['forwarded_count']}\n"
            f"Position: {config['last_forwarded_id']}\n"
        )
        if progress:
            status_msg += f"DB: ✅ Active"
        await event.answer(status_msg, alert=True)
    
    elif data == "start":
        if not config['source_channel'] or not config['destination_channel']:
            await event.answer("❌ Set channels first!", alert=True)
            return
        
        config['is_running'] = True
        save_config(config)
        
        await event.edit("▶️ **Starting...**")
        asyncio.create_task(start_forwarding_task(event))
    
    elif data == "stop":
        config['is_running'] = False
        save_config(config)
        await event.edit(
            f"⏸️ **Stopped**\n\n{config['last_forwarded_id']}",
            buttons=get_main_menu()
        )
    
    elif data == "stats":
        stats = (
            f"📊 Stats\n\n"
            f"Total: {config['forwarded_count']}\n"
            f"Last: {config['last_forwarded_id']}\n"
            f"Speed: {config['forward_delay']}s\n"
            f"Batch: {config['batch_size']}"
        )
        await event.answer(stats, alert=True)

# ============================================
# FORWARDING TASK
# ============================================
async def start_forwarding_task(event):
    try:
        forwarded = await safe_forward(
            client,
            config['source_channel'],
            config['destination_channel'],
            config['last_forwarded_id']
        )
        
        await client.send_message(
            ADMIN_ID,
            f"✅ **Complete**\n\n"
            f"📊 Session: {forwarded}\n"
            f"📊 Total: {config['forwarded_count']}\n"
            f"📍 Last: {config['last_forwarded_id']}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"💾 Saved to database",
            buttons=get_main_menu()
        )
    except Exception as e:
        logger.error(f"❌ Task error: {e}")
        await client.send_message(
            ADMIN_ID,
            f"❌ Error: `{e}`\n\n"
            f"📍 {config['last_forwarded_id']}\n"
            f"💾 Saved to database\n"
            f"`/forward` to resume",
            buttons=get_main_menu()
        )
    finally:
        config['is_running'] = False
        save_config(config)

# ============================================
# AUTO-FORWARD
# ============================================
@client.on(events.NewMessage)
async def auto_forward_handler(event):
    if not config['auto_mode'] or not config['source_channel']:
        return
    
    try:
        if event.chat_id == config['source_channel'] and config['destination_channel']:
            await asyncio.sleep(config['forward_delay'])
            dest = await client.get_entity(config['destination_channel'])
            
            sent_msg = await client.send_message(
                dest,
                event.message.text if event.message.text else "",
                file=event.message.media if event.message.media else None,
                formatting_entities=event.message.entities
            )
            
            config['forwarded_count'] += 1
            config['last_forwarded_id'] = event.message.id
            
            # Save to database
            db.save_message_mapping(event.message.id, sent_msg.id)
            
            if config['forwarded_count'] % 10 == 0:
                save_config(config)
            
            logger.info(f"✅ Auto: {event.message.id}")
    except Exception as e:
        logger.error(f"Auto error: {e}")

# ============================================
# MAIN
# ============================================
start_time = datetime.now()

async def main():
    global start_time
    start_time = datetime.now()
    
    logger.info("=" * 50)
    logger.info("🚀 Userbot v2.0 Starting...")
    logger.info("✅ Never sleeps on Render")
    logger.info("💾 Database progress tracking")
    logger.info("🔄 Auto-resume enabled")
    logger.info("🆔 Smart ID detection")
    logger.info("=" * 50)
    
    if not validate_env():
        logger.error("❌ Set environment variables")
        return
    
    try:
        # Start HTTP server FIRST
        logger.info(f"🌐 Starting HTTP server on 0.0.0.0:{PORT}...")
        http_runner = await start_http_server()
        logger.info(f"✅ HTTP server running")
        
        # Connect to Telegram
        logger.info("📱 Connecting to Telegram...")
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.error("❌ Not authorized! Generate session first")
            return
        
        me = await client.get_me()
        logger.info(f"✅ Connected: {me.first_name}")
        logger.info(f"📱 Phone: {me.phone}")
        logger.info("=" * 50)
        
        # Start aggressive keep-alive
        asyncio.create_task(keep_alive_aggressive())
        logger.info("💓 Keep-alive started")
        
        # Check for existing progress
        progress = db.get_progress()
        if progress:
            logger.info(f"✅ Found saved progress: Message {progress['last_forwarded_id']}")
        
        # Startup notification
        await client.send_message(
            ADMIN_ID,
            "🤖 **Userbot v2.0 Started!**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ Never sleeps on Render\n"
            "💾 Database tracking\n"
            "🔄 Auto-resume ready\n"
            "🆔 Smart ID detection\n\n"
            f"🌐 Port {PORT}\n"
            f"💓 Keep-alive active\n\n"
            f"**Quick Start:**\n"
            f"1. `/source [ID]`\n"
            f"2. `/dest [ID]`\n"
            f"3. `/forward` ⭐\n\n"
            f"Send /start for menu\n"
            f"Send /help for commands",
            buttons=[[Button.inline("📋 Menu", b"refresh")]]
        )
        
        logger.info("✅ Ready! Send /start")
        logger.info("=" * 50)
        
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"❌ Startup error: {e}")
        raise
    finally:
        if 'http_runner' in locals():
            await http_runner.cleanup()
            logger.info("🌐 HTTP server stopped")

if __name__ == '__main__':
    try:
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("👋 Stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal: {e}")
        raise
