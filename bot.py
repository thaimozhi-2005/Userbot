"""
Telegram Channel Auto-Forwarder Userbot
Works with Channel IDs (no admin access needed)
Optimized for Ubuntu & Render deployment
WITH HTTP SERVER FOR RENDER PORT BINDING
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
# CONFIGURATION - USE ENVIRONMENT VARIABLES
# ============================================
API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', 'YOUR_API_HASH')
PHONE = os.getenv('PHONE', 'YOUR_PHONE_NUMBER')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
PORT = int(os.getenv('PORT', '10000'))  # Render assigns this automatically

SESSION_FILE = os.getenv('SESSION_FILE', 'userbot_session')
CONFIG_FILE = 'bot_config.json'

# ============================================
# HTTP HEALTH CHECK SERVER FOR RENDER
# ============================================
async def health_check(request):
    """Health check endpoint for Render"""
    return web.json_response({
        'status': 'healthy',
        'bot_running': config.get('is_running', False),
        'forwarded_count': config.get('forwarded_count', 0),
        'last_id': config.get('last_forwarded_id', 0),
        'timestamp': datetime.now().isoformat()
    })

async def root_handler(request):
    """Root endpoint"""
    status = "🟢 Running" if config.get('is_running', False) else "🔴 Stopped"
    return web.Response(text=f"""
╔══════════════════════════════════════╗
║   TELEGRAM USERBOT - ACTIVE          ║
╚══════════════════════════════════════╝

Status: {status}
Total Forwarded: {config.get('forwarded_count', 0)} messages
Last Message ID: {config.get('last_forwarded_id', 0)}
Server Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Bot is running successfully on Render! ✅
""", content_type='text/plain')

async def start_http_server():
    """Start HTTP server for Render health checks"""
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/health', health_check)
    app.router.add_get('/status', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 HTTP server started on 0.0.0.0:{PORT}")
    return runner

# ============================================
# VALIDATE ENVIRONMENT VARIABLES
# ============================================
def validate_env():
    """Check if all required env variables are set"""
    required = ['API_ID', 'API_HASH', 'PHONE', 'ADMIN_ID']
    missing = [var for var in required if not os.getenv(var)]
    
    if missing:
        logger.error(f"❌ Missing environment variables: {', '.join(missing)}")
        logger.info("Set them using: export VAR_NAME=value")
        return False
    
    logger.info("✅ All environment variables configured")
    return True

# ============================================
# HELPER: Extract Channel ID
# ============================================
def extract_channel_id(text):
    """
    Extract channel ID from various formats:
    - Direct ID: -1002616886749
    - Username: @channelname (will be converted to ID)
    - Returns the ID as integer or string
    """
    text = text.strip()
    
    if text.startswith('-') and text[1:].isdigit():
        return int(text)
    
    if text.startswith('@'):
        return text
    
    try:
        return int(text)
    except ValueError:
        return text

# ============================================
# DEFAULT CONFIGURATION
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
    'notify_batch': True,  # NEW: Notify on batch completion
    'notify_interval': 50,  # NEW: Notify every N messages
}

# ============================================
# LOAD/SAVE CONFIG
# ============================================
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                logger.info("✅ Config loaded from file")
                return config
        except Exception as e:
            logger.error(f"❌ Error loading config: {e}")
    
    logger.info("📝 Using default config")
    return default_config.copy()

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        logger.info("💾 Config saved")
    except Exception as e:
        logger.error(f"❌ Error saving config: {e}")

config = load_config()

# ============================================
# SESSION HANDLING (File or String)
# ============================================
def get_session():
    """Get session - prioritize string session from env"""
    session_string = os.getenv('SESSION_STRING')
    
    if session_string:
        logger.info("🔑 Using StringSession from environment")
        return StringSession(session_string)
    
    session_b64 = os.getenv('SESSION_DATA')
    if session_b64 and not os.path.exists(f"{SESSION_FILE}.session"):
        try:
            import base64
            session_bytes = base64.b64decode(session_b64)
            with open(f"{SESSION_FILE}.session", 'wb') as f:
                f.write(session_bytes)
            logger.info("✅ Session file created from SESSION_DATA")
        except Exception as e:
            logger.error(f"❌ Error creating session file: {e}")
    
    if os.path.exists(f"{SESSION_FILE}.session"):
        logger.info("📁 Using file session")
        return SESSION_FILE
    
    logger.warning("⚠️ No session found - will need to authenticate")
    return SESSION_FILE

# ============================================
# INITIALIZE CLIENT
# ============================================
client = TelegramClient(get_session(), API_ID, API_HASH)

# ============================================
# KEEP-ALIVE FOR RENDER
# ============================================
async def keep_alive_task():
    """Send periodic pings to prevent Render from sleeping"""
    while config.get('keep_alive', True):
        try:
            await asyncio.sleep(600)  # Every 10 minutes
            logger.info("💓 Keep-alive ping")
            
            # Send status to admin every hour
            if datetime.now().minute == 0:
                status = "🟢 Running" if config['is_running'] else "🔴 Idle"
                await client.send_message(
                    ADMIN_ID,
                    f"💓 **Hourly Status Report**\n\n"
                    f"Status: {status}\n"
                    f"Total Forwarded: {config['forwarded_count']}\n"
                    f"Last ID: {config['last_forwarded_id']}\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}"
                )
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
            await asyncio.sleep(60)

# ============================================
# ADMIN PANEL BUTTONS
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

def get_settings_menu():
    return [
        [Button.inline(f"⏱️ Delay: {config['forward_delay']}s", b"set_delay")],
        [Button.inline(f"📦 Batch: {config['batch_size']}", b"set_batch")],
        [Button.inline(f"⏰ Batch Delay: {config['batch_delay']}s", b"set_batch_delay")],
        [Button.inline("🔔 Notifications", b"notifications")],
        [Button.inline("🔙 Back", b"back")]
    ]

# ============================================
# GET CHANNEL INFO
# ============================================
async def get_channel_info(channel_id):
    """Get channel information to display to user"""
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
# SAFE FORWARDING WITH ANTI-SPAM - IMPROVED
# ============================================
async def safe_forward(client, source_id, dest_id, start_id=0):
    """Safely forward messages with anti-spam measures - NO FORWARD TAG"""
    try:
        logger.info(f"🚀 Starting forward from {source_id} to {dest_id}")
        source = await client.get_entity(source_id)
        dest = await client.get_entity(dest_id)
        
        # Initial notification
        await client.send_message(
            ADMIN_ID,
            f"🚀 **Forwarding Started!**\n\n"
            f"📥 From: {getattr(source, 'title', 'Source')}\n"
            f"📤 To: {getattr(dest, 'title', 'Destination')}\n"
            f"🔄 Starting from ID: {start_id + 1}\n\n"
            f"Speed: {config['forward_delay']}s delay\n"
            f"Batch: {config['batch_size']} msgs\n"
            f"Rest: {config['batch_delay']}s"
        )
        
        forwarded = 0
        batch_count = 0
        last_notified = 0
        
        async for message in client.iter_messages(source, min_id=start_id, reverse=True):
            if not config['is_running']:
                logger.info("⏸️ Forwarding stopped by user")
                await client.send_message(
                    ADMIN_ID,
                    f"⏸️ **Forwarding Paused**\n\n"
                    f"✅ Forwarded: {forwarded} messages\n"
                    f"🔄 Last ID: {config['last_forwarded_id']}\n"
                    f"➡️ Resume from: {config['last_forwarded_id'] + 1}\n\n"
                    f"Use `/forward` to resume"
                )
                break
            
            # Skip media types if configured
            if message.media and hasattr(message.media, '__class__'):
                media_type = message.media.__class__.__name__.lower()
                if any(skip in media_type for skip in config['skip_media_types']):
                    logger.info(f"⏭️ Skipped {media_type}")
                    continue
            
            try:
                # Send as new message (NO FORWARD TAG)
                await client.send_message(
                    dest,
                    message.text if message.text else "",
                    file=message.media if message.media else None,
                    formatting_entities=message.entities
                )
                
                forwarded += 1
                batch_count += 1
                config['forwarded_count'] += 1
                config['last_forwarded_id'] = message.id
                
                # Save config every 10 messages
                if forwarded % 10 == 0:
                    save_config(config)
                
                # IMPROVED: Notify every N messages
                if config.get('notify_batch', True) and forwarded - last_notified >= config.get('notify_interval', 50):
                    await client.send_message(
                        ADMIN_ID,
                        f"📊 **Progress Update**\n\n"
                        f"✅ Forwarded: {forwarded} messages\n"
                        f"🔄 Current ID: {message.id}\n"
                        f"⏱️ Speed: {config['forward_delay']}s/msg\n\n"
                        f"Use `/setid {message.id}` to resume from here"
                    )
                    last_notified = forwarded
                    logger.info(f"📊 Progress: {forwarded} messages forwarded")
                
                # Delay between messages
                await asyncio.sleep(config['forward_delay'])
                
                # IMPROVED: Batch delay with detailed notification
                if batch_count >= config['batch_size']:
                    logger.info(f"✅ Batch complete: {batch_count} messages")
                    
                    # Calculate estimated completion time
                    messages_per_second = 1 / config['forward_delay']
                    estimated_remaining = (10000 / messages_per_second) / 3600  # rough estimate
                    
                    await client.send_message(
                        ADMIN_ID,
                        f"✅ **Batch Complete!**\n\n"
                        f"📦 Batch Size: {batch_count} messages\n"
                        f"🔄 Last ID: {message.id}\n"
                        f"📊 Total: {config['forwarded_count']}\n\n"
                        f"⏸️ Resting for {config['batch_delay']}s ({config['batch_delay']//60} min)\n"
                        f"⏱️ Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
                        f"💡 Resume command: `/setid {message.id}`"
                    )
                    await asyncio.sleep(config['batch_delay'])
                    batch_count = 0
                    
            except Exception as e:
                logger.error(f"❌ Error forwarding msg {message.id}: {e}")
                
                # Notify on critical errors
                if "flood" in str(e).lower():
                    await client.send_message(
                        ADMIN_ID,
                        f"⚠️ **Flood Warning!**\n\n"
                        f"Telegram detected high activity.\n"
                        f"Last successful: {config['last_forwarded_id']}\n\n"
                        f"Bot will slow down automatically."
                    )
                    await asyncio.sleep(60)  # Extra delay on flood
                else:
                    await asyncio.sleep(5)
                continue
        
        save_config(config)
        logger.info(f"✅ Forwarding complete: {forwarded} total")
        return forwarded
        
    except Exception as e:
        logger.error(f"❌ Forward error: {e}")
        await client.send_message(
            ADMIN_ID,
            f"❌ **Critical Error**\n\n"
            f"Error: `{str(e)}`\n"
            f"Last ID: {config['last_forwarded_id']}\n\n"
            f"Use `/setid {config['last_forwarded_id']}` to resume"
        )
        return 0

# ============================================
# COMMAND HANDLERS
# ============================================
@client.on(events.NewMessage(pattern='/start', from_users=ADMIN_ID))
async def start_handler(event):
    logger.info("📋 Main menu requested")
    
    source_info = f"`{config['source_channel']}`" if config['source_channel'] else "❌ Not set"
    dest_info = f"`{config['destination_channel']}`" if config['destination_channel'] else "❌ Not set"
    status = "🟢 Running" if config['is_running'] else "🔴 Stopped"
    
    await event.respond(
        "🤖 **Channel Forwarder Userbot**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🆔 Works with Channel IDs\n"
        "🖥️ Running on Render\n"
        f"🌐 Port: {PORT}\n\n"
        f"**Current Status:**\n"
        f"Status: {status}\n"
        f"📊 Total: {config['forwarded_count']} msgs\n"
        f"🔄 Last ID: {config['last_forwarded_id']}\n"
        f"📥 Source: {source_info}\n"
        f"📤 Dest: {dest_info}\n\n"
        f"**Quick Commands:**\n"
        "`/forward` - Start forwarding\n"
        "`/stopforward` - Stop\n"
        "`/status` - Full status\n"
        "`/progress` - Check progress\n\n"
        "`/source [ID]` - Set source\n"
        "`/dest [ID]` - Set destination\n"
        "`/speed balanced` - Set speed ⭐\n\n"
        "`/reset confirm` - Reset progress\n"
        "`/setid [number]` - Set start ID\n\n"
        "**📋 Use buttons below for easy control!**",
        buttons=get_main_menu()
    )

@client.on(events.NewMessage(pattern='/menu', from_users=ADMIN_ID))
async def menu_handler(event):
    await event.respond("📋 **Control Panel**", buttons=get_main_menu())

@client.on(events.NewMessage(pattern='/stop', from_users=ADMIN_ID))
async def stop_handler(event):
    config['is_running'] = False
    save_config(config)
    logger.info("⏹️ Bot stopped by command")
    await event.respond(
        f"⏹️ **Stopped!**\n\n"
        f"Last ID: {config['last_forwarded_id']}\n"
        f"Use `/forward` to resume",
        buttons=get_main_menu()
    )

@client.on(events.NewMessage(pattern='/logs', from_users=ADMIN_ID))
async def logs_handler(event):
    """Send last 30 lines of logs"""
    try:
        if os.path.exists('bot.log'):
            with open('bot.log', 'r') as f:
                lines = f.readlines()
                last_lines = ''.join(lines[-30:])
                # Split into chunks if too long
                if len(last_lines) > 3500:
                    chunks = [last_lines[i:i+3500] for i in range(0, len(last_lines), 3500)]
                    for i, chunk in enumerate(chunks):
                        await event.respond(f"📄 **Logs Part {i+1}/{len(chunks)}:**\n\n```\n{chunk}\n```")
                else:
                    await event.respond(f"📄 **Last 30 log lines:**\n\n```\n{last_lines}\n```")
        else:
            await event.respond("❌ No log file found")
    except Exception as e:
        await event.respond(f"❌ Error reading logs: {e}")

@client.on(events.NewMessage(pattern='/health', from_users=ADMIN_ID))
async def health_handler(event):
    """Health check for Render"""
    uptime_start = datetime.now()  # You can store actual start time
    await event.respond(
        f"💚 **Bot Health Check**\n\n"
        f"✅ Status: Online\n"
        f"🌐 HTTP Server: Running on port {PORT}\n"
        f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}\n"
        f"📊 Forwarded: {config['forwarded_count']}\n"
        f"🔄 Last ID: {config['last_forwarded_id']}\n"
        f"🤖 Auto Mode: {'ON' if config['auto_mode'] else 'OFF'}\n\n"
        f"All systems operational! ✅"
    )

@client.on(events.NewMessage(pattern='/getid', from_users=ADMIN_ID))
async def getid_handler(event):
    """Get channel ID from forwarded message or reply"""
    if event.is_reply:
        replied = await event.get_reply_message()
        if replied.forward:
            channel_id = replied.forward.from_id
            await event.respond(
                f"🆔 **Channel ID Found:**\n\n"
                f"`{channel_id.channel_id if hasattr(channel_id, 'channel_id') else channel_id}`\n\n"
                f"**Copy and use:**\n"
                f"`/source {channel_id.channel_id if hasattr(channel_id, 'channel_id') else channel_id}`\n"
                f"or\n"
                f"`/dest {channel_id.channel_id if hasattr(channel_id, 'channel_id') else channel_id}`"
            )
        else:
            await event.respond("❌ Not a forwarded message")
    else:
        await event.respond(
            "💡 **How to get Channel ID:**\n\n"
            "**Method 1:**\n"
            "1. Forward any message from channel to @userinfobot\n"
            "2. Bot will show the Channel ID\n\n"
            "**Method 2:**\n"
            "1. Forward a message from the channel to me\n"
            "2. Reply to it with /getid\n\n"
            "**Method 3:**\n"
            "Use @getidsbot in Telegram\n\n"
            "Channel IDs look like: `-1002616886749`"
        )

# ============================================
# BUTTON CALLBACKS - FIXED FOR TELEGRAM DISPLAY
# ============================================
@client.on(events.CallbackQuery)
async def callback_handler(event):
    if event.sender_id != int(ADMIN_ID):
        await event.answer("❌ Unauthorized!", alert=True)
        return
    
    data = event.data.decode('utf-8')
    logger.info(f"🔘 Button clicked: {data}")
    
    if data == "refresh":
        status = "🟢 Running" if config['is_running'] else "🔴 Stopped"
        await event.edit(
            f"🤖 **Channel Forwarder**\n\n"
            f"Status: {status}\n"
            f"📊 Forwarded: {config['forwarded_count']}\n"
            f"🔄 Last ID: {config['last_forwarded_id']}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}",
            buttons=get_main_menu()
        )
    
    elif data == "status":
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
        
        status_msg = (
            f"📊 Bot Status\n\n"
            f"📥 Source:\n{source_info}\n\n"
            f"📤 Destination:\n{dest_info}\n\n"
            f"Running: {'✅' if config['is_running'] else '❌'}\n"
            f"Auto: {'✅' if config['auto_mode'] else '❌'}\n"
            f"Forwarded: {config['forwarded_count']}\n"
            f"Last ID: {config['last_forwarded_id']}"
        )
        await event.answer(status_msg, alert=True)
    
    elif data == "set_source":
        await event.edit(
            "📥 **Set Source Channel ID**\n\n"
            "Send command:\n"
            "`/source -1002616886749`\n\n"
            "💡 Get Channel ID:\n"
            "Forward message to @userinfobot",
            buttons=[[Button.inline("🔙 Back", b"back")]]
        )
    
    elif data == "set_dest":
        await event.edit(
            "📤 **Set Destination Channel ID**\n\n"
            "Send command:\n"
            "`/dest -1002616886749`\n\n"
            "💡 Get Channel ID:\n"
            "Forward message to @userinfobot",
            buttons=[[Button.inline("🔙 Back", b"back")]]
        )
    
    elif data == "start":
        if not config['source_channel'] or not config['destination_channel']:
            await event.answer("❌ Set source and destination first!", alert=True)
            return
        
        config['is_running'] = True
        save_config(config)
        logger.info("▶️ Forwarding started")
        
        await event.edit("▶️ **Starting...**\n\nPlease wait...")
        asyncio.create_task(start_forwarding_task(event))
    
    elif data == "stop":
        config['is_running'] = False
        save_config(config)
        logger.info("⏸️ Forwarding stopped")
        await event.edit(
            f"⏸️ **Stopped!**\n\n"
            f"Last ID: {config['last_forwarded_id']}",
            buttons=get_main_menu()
        )
    
    elif data == "toggle_auto":
        config['auto_mode'] = not config['auto_mode']
        save_config(config)
        mode = "ON" if config['auto_mode'] else "OFF"
        logger.info(f"🤖 Auto mode: {config['auto_mode']}")
        await event.edit(
            f"🤖 **Auto Mode: {mode}**\n\n"
            f"New messages will be {'forwarded' if config['auto_mode'] else 'ignored'}",
            buttons=get_main_menu()
        )
    
    elif data == "settings":
        await event.edit("⚙️ **Settings Menu**", buttons=get_settings_menu())
    
    elif data == "notifications":
        notify_status = "ON" if config.get('notify_batch', True) else "OFF"
        await event.edit(
            f"🔔 **Notification Settings**\n\n"
            f"Status: {notify_status}\n"
            f"Interval: Every {config.get('notify_interval', 50)} messages\n\n"
            f"Use `/notify on` or `/notify off`\n"
            f"Use `/notifyinterval [number]` to change",
            buttons=[[Button.inline("🔙 Back", b"settings")]]
        )
    
    elif data == "stats":
        stats_msg = (
            f"📊 Statistics\n\n"
            f"Total: {config['forwarded_count']}\n"
            f"Last ID: {config['last_forwarded_id']}\n"
            f"Delay: {config['forward_delay']}s\n"
            f"Batch: {config['batch_size']}\n"
            f"Batch Delay: {config['batch_delay']}s"
        )
        await event.answer(stats_msg, alert=True)
    
    elif data == "back":
        await event.edit("📋 **Main Menu**", buttons=get_main_menu())

# ============================================
# CONFIG COMMANDS
# ============================================
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
            f"✅ **Source Channel Set!**\n\n"
            f"{info}\n\n"
            f"Now set destination with:\n"
            f"`/dest [channel_id]`",
            buttons=get_main_menu()
        )
    except IndexError:
        await event.respond(
            "❌ **Usage:**\n"
            "`/source -1002616886749`\n\n"
            "Use /getid for help"
        )
    except Exception as e:
        await event.respond(
            f"❌ **Error:**\n`{str(e)}`\n\n"
            "Make sure:\n"
            "1. Channel ID is correct\n"
            "2. You're subscribed\n"
            "3. Channel exists"
        )

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
            f"✅ **Destination Channel Set!**\n\n"
            f"{info}\n\n"
            f"All set! Use `/forward` to start!",
            buttons=get_main_menu()
        )
    except IndexError:
        await event.respond(
            "❌ **Usage:**\n"
            "`/dest -1002616886749`\n\n"
            "Use /getid for help"
        )
    except Exception as e:
        await event.respond(
            f"❌ **Error:**\n`{str(e)}`\n\n"
            "Make sure:\n"
            "1. Channel ID is correct\n"
            "2. You have admin rights\n"
            "3. Channel exists"
        )

@client.on(events.NewMessage(pattern='/forward', from_users=ADMIN_ID))
async def forward_command(event):
    """Start forwarding without buttons"""
    if not config['source_channel'] or not config['destination_channel']:
        await event.respond(
            "❌ **Setup Required!**\n\n"
            "Set channels first:\n"
            "`/source [ID]`\n"
            "`/dest [ID]`"
        )
        return
    
    if config['is_running']:
        await event.respond("⚠️ Already running!\n\nUse `/stopforward` to stop.")
        return
    
    config['is_running'] = True
    save_config(config)
    logger.info("▶️ Forwarding started via command")
    
    await event.respond(
        "▶️ **Starting forwarding...**\n\n"
        f"From ID: {config['last_forwarded_id'] + 1}\n"
        f"Speed: {config['forward_delay']}s\n\n"
        "Use `/stopforward` to stop"
    )
    asyncio.create_task(start_forwarding_task(event))

@client.on(events.NewMessage(pattern='/stopforward', from_users=ADMIN_ID))
async def stopforward_command(event):
    """Stop forwarding without buttons"""
    config['is_running'] = False
    save_config(config)
    logger.info("⏸️ Forwarding stopped via command")
    await event.respond(
        f"⏸️ **Stopped!**\n\n"
        f"Last ID: {config['last_forwarded_id']}\n"
        f"Resume: `/forward`"
    )

@client.on(events.NewMessage(pattern='/auto', from_users=ADMIN_ID))
async def auto_command(event):
    """Toggle auto mode"""
    try:
        mode = event.text.split()[1].lower()
        if mode == 'on':
            config['auto_mode'] = True
            await event.respond(
                "✅ **Auto-forward: ON**\n\n"
                "New messages will be forwarded automatically!",
                buttons=get_main_menu()
            )
        elif mode == 'off':
            config['auto_mode'] = False
            await event.respond(
                "✅ **Auto-forward: OFF**",
                buttons=get_main_menu()
            )
        else:
            await event.respond("❌ Usage: `/auto on` or `/auto off`")
        save_config(config)
    except:
        current = "ON" if config['auto_mode'] else "OFF"
        await event.respond(
            f"🤖 **Auto-forward: {current}**\n\n"
            f"Usage:\n"
            f"`/auto on` - Enable\n"
            f"`/auto off` - Disable"
        )

@client.on(events.NewMessage(pattern='/status', from_users=ADMIN_ID))
async def status_command(event):
    """Check status without buttons"""
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
    
    await event.respond(
        f"📊 **Bot Status**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Channels:**\n"
        f"📥 Source:\n{source_info}\n\n"
        f"📤 Destination:\n{dest_info}\n\n"
        f"**Status:**\n"
        f"Running: {status}\n"
        f"Auto Mode: {auto}\n"
        f"Total: {config['forwarded_count']} msgs\n"
        f"Last ID: {config['last_forwarded_id']}\n\n"
        f"**Settings:**\n"
        f"⏱️ Delay: {config['forward_delay']}s\n"
        f"📦 Batch: {config['batch_size']}\n"
        f"⏰ Rest: {config['batch_delay']}s\n"
        f"🔔 Notify: Every {config.get('notify_interval', 50)} msgs",
        buttons=get_main_menu()
    )

@client.on(events.NewMessage(pattern='/reset', from_users=ADMIN_ID))
async def reset_command(event):
    """Reset forwarding progress"""
    try:
        confirm = event.text.split()[1].lower() if len(event.text.split()) > 1 else ""
        
        if confirm == "confirm":
            old_count = config['forwarded_count']
            old_id = config['last_forwarded_id']
            
            config['last_forwarded_id'] = 0
            config['forwarded_count'] = 0
            save_config(config)
            
            await event.respond(
                f"✅ **Progress Reset!**\n\n"
                f"**Previous:**\n"
                f"Count: {old_count}\n"
                f"Last ID: {old_id}\n\n"
                f"**New:**\n"
                f"Count: 0\n"
                f"Last ID: 0\n\n"
                f"Next `/forward` starts from beginning!",
                buttons=get_main_menu()
            )
            logger.info("🔄 Progress reset to 0")
        else:
            await event.respond(
                f"⚠️ **Confirm Reset?**\n\n"
                f"Current:\n"
                f"Forwarded: {config['forwarded_count']}\n"
                f"Last ID: {config['last_forwarded_id']}\n\n"
                f"⚠️ Will start from beginning!\n"
                f"May create duplicates!\n\n"
                f"Confirm: `/reset confirm`"
            )
    except Exception as e:
        await event.respond(f"❌ Error: {e}")

@client.on(events.NewMessage(pattern='/setid', from_users=ADMIN_ID))
async def setid_command(event):
    """Set custom starting message ID"""
    try:
        msg_id = int(event.text.split()[1])
        
        if msg_id < 0:
            msg_id = 0
        
        old_id = config['last_forwarded_id']
        config['last_forwarded_id'] = msg_id
        save_config(config)
        
        await event.respond(
            f"✅ **Starting ID Updated!**\n\n"
            f"Previous: {old_id}\n"
            f"New: {msg_id}\n\n"
            f"Next `/forward` starts from: {msg_id + 1}",
            buttons=get_main_menu()
        )
        logger.info(f"🔄 Starting ID set to: {msg_id}")
        
    except (IndexError, ValueError):
        await event.respond(
            f"❌ **Usage:** `/setid [message_id]`\n\n"
            f"Current: {config['last_forwarded_id']}\n\n"
            f"**Examples:**\n"
            f"`/setid 0` - From beginning\n"
            f"`/setid 5000` - From msg 5001"
        )

@client.on(events.NewMessage(pattern='/progress', from_users=ADMIN_ID))
async def progress_command(event):
    """Check forwarding progress"""
    status = "🟢 Running" if config['is_running'] else "🔴 Stopped"
    
    # Calculate estimated time if running
    if config['is_running']:
        est_text = "Calculating..."
    else:
        est_text = "Not running"
    
    await event.respond(
        f"📊 **Forwarding Progress**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Status: {status}\n\n"
        f"**Progress:**\n"
        f"✅ Total: {config['forwarded_count']} msgs\n"
        f"🔄 Last ID: {config['last_forwarded_id']}\n"
        f"➡️ Next: Message {config['last_forwarded_id'] + 1}\n\n"
        f"**Speed:**\n"
        f"⏱️ Delay: {config['forward_delay']}s/msg\n"
        f"📦 Batch: {config['batch_size']} msgs\n"
        f"⏰ Rest: {config['batch_delay']}s after batch\n\n"
        f"Use `/setid {config['last_forwarded_id']}` to resume",
        buttons=get_main_menu()
    )

@client.on(events.NewMessage(pattern='/delay', from_users=ADMIN_ID))
async def set_delay(event):
    try:
        delay = int(event.text.split()[1])
        if delay < 1:
            delay = 1
        config['forward_delay'] = delay
        save_config(config)
        logger.info(f"⏱️ Delay set: {delay}s")
        await event.respond(
            f"✅ **Message delay: {delay}s**\n\n"
            f"Recommended: 2-3s for safety",
            buttons=get_main_menu()
        )
    except:
        await event.respond(
            f"❌ **Usage:** `/delay [seconds]`\n\n"
            f"Current: {config['forward_delay']}s\n"
            f"Recommended: 2-3s"
        )

@client.on(events.NewMessage(pattern='/batchsize', from_users=ADMIN_ID))
async def set_batch_size(event):
    try:
        size = int(event.text.split()[1])
        if size < 10:
            size = 10
        if size > 200:
            size = 200
        config['batch_size'] = size
        save_config(config)
        logger.info(f"📦 Batch size set: {size}")
        await event.respond(
            f"✅ **Batch size: {size} msgs**\n\n"
            f"Rest delay: {config['batch_delay']}s",
            buttons=get_main_menu()
        )
    except:
        await event.respond(
            f"❌ **Usage:** `/batchsize [number]`\n\n"
            f"Current: {config['batch_size']}\n"
            f"Range: 10-200"
        )

@client.on(events.NewMessage(pattern='/batchdelay', from_users=ADMIN_ID))
async def set_batch_delay(event):
    try:
        delay = int(event.text.split()[1])
        if delay < 30:
            delay = 30
        config['batch_delay'] = delay
        save_config(config)
        logger.info(f"⏰ Batch delay set: {delay}s")
        await event.respond(
            f"✅ **Batch delay: {delay}s**\n"
            f"({delay//60} min {delay%60}s)\n\n"
            f"Batch size: {config['batch_size']}",
            buttons=get_main_menu()
        )
    except:
        await event.respond(
            f"❌ **Usage:** `/batchdelay [seconds]`\n\n"
            f"Current: {config['batch_delay']}s\n"
            f"Recommended: 120s (2 min)"
        )

@client.on(events.NewMessage(pattern='/notify', from_users=ADMIN_ID))
async def notify_command(event):
    """Toggle notification settings"""
    try:
        mode = event.text.split()[1].lower()
        if mode == 'on':
            config['notify_batch'] = True
            await event.respond(
                "✅ **Notifications: ON**\n\n"
                f"You'll get updates every {config.get('notify_interval', 50)} msgs",
                buttons=get_main_menu()
            )
        elif mode == 'off':
            config['notify_batch'] = False
            await event.respond(
                "✅ **Notifications: OFF**\n\n"
                "Only batch completion alerts",
                buttons=get_main_menu()
            )
        else:
            await event.respond("❌ Usage: `/notify on` or `/notify off`")
        save_config(config)
    except:
        current = "ON" if config.get('notify_batch', True) else "OFF"
        await event.respond(
            f"🔔 **Notifications: {current}**\n\n"
            f"Interval: Every {config.get('notify_interval', 50)} msgs\n\n"
            f"Commands:\n"
            f"`/notify on` - Enable\n"
            f"`/notify off` - Disable\n"
            f"`/notifyinterval [num]` - Change interval"
        )

@client.on(events.NewMessage(pattern='/notifyinterval', from_users=ADMIN_ID))
async def set_notify_interval(event):
    """Set notification interval"""
    try:
        interval = int(event.text.split()[1])
        if interval < 10:
            interval = 10
        if interval > 500:
            interval = 500
        config['notify_interval'] = interval
        save_config(config)
        await event.respond(
            f"✅ **Notify interval: {interval} msgs**\n\n"
            "You'll get progress updates accordingly",
            buttons=get_main_menu()
        )
    except:
        await event.respond(
            f"❌ **Usage:** `/notifyinterval [number]`\n\n"
            f"Current: {config.get('notify_interval', 50)}\n"
            f"Range: 10-500"
        )

@client.on(events.NewMessage(pattern='/speed', from_users=ADMIN_ID))
async def set_speed_preset(event):
    """Quick speed presets"""
    try:
        preset = event.text.split()[1].lower()
        
        if preset == 'safe':
            config['forward_delay'] = 3
            config['batch_size'] = 50
            config['batch_delay'] = 300
            desc = "🐢 Safe - Slowest, safest"
            
        elif preset == 'balanced':
            config['forward_delay'] = 2
            config['batch_size'] = 100
            config['batch_delay'] = 120
            desc = "⚖️ Balanced - Recommended ⭐"
            
        elif preset == 'fast':
            config['forward_delay'] = 1
            config['batch_size'] = 150
            config['batch_delay'] = 90
            desc = "🚀 Fast - Quick, small risk"
            
        elif preset == 'turbo':
            config['forward_delay'] = 1
            config['batch_size'] = 200
            config['batch_delay'] = 60
            desc = "⚡ Turbo - Fastest, risky"
            
        else:
            await event.respond(
                "❌ Invalid preset!\n\n"
                "**Available:**\n"
                "`/speed safe`\n"
                "`/speed balanced` ⭐\n"
                "`/speed fast`\n"
                "`/speed turbo`"
            )
            return
        
        save_config(config)
        await event.respond(
            f"✅ **{desc}**\n\n"
            f"⏱️ Delay: {config['forward_delay']}s\n"
            f"📦 Batch: {config['batch_size']}\n"
            f"⏰ Rest: {config['batch_delay']}s",
            buttons=get_main_menu()
        )
        
    except IndexError:
        await event.respond(
            "⚙️ **Speed Presets:**\n\n"
            f"**Current:**\n"
            f"⏱️ {config['forward_delay']}s\n"
            f"📦 {config['batch_size']}\n"
            f"⏰ {config['batch_delay']}s\n\n"
            "**Available:**\n"
            "`/speed safe` - 🐢 Safest\n"
            "`/speed balanced` - ⚖️ Best ⭐\n"
            "`/speed fast` - 🚀 Quick\n"
            "`/speed turbo` - ⚡ Fastest"
        )

# NEW: Help command
@client.on(events.NewMessage(pattern='/help', from_users=ADMIN_ID))
async def help_command(event):
    """Show all commands"""
    await event.respond(
        "📚 **All Commands**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Setup:**\n"
        "`/source [ID]` - Set source\n"
        "`/dest [ID]` - Set destination\n"
        "`/getid` - Get channel ID help\n\n"
        "**Control:**\n"
        "`/forward` - Start forwarding\n"
        "`/stopforward` - Stop\n"
        "`/auto on/off` - Toggle auto mode\n\n"
        "**Progress:**\n"
        "`/status` - Full status\n"
        "`/progress` - Check progress\n"
        "`/setid [num]` - Set start ID\n"
        "`/reset confirm` - Reset progress\n\n"
        "**Speed:**\n"
        "`/speed balanced` - Set speed ⭐\n"
        "`/delay [sec]` - Message delay\n"
        "`/batchsize [num]` - Batch size\n"
        "`/batchdelay [sec]` - Batch rest\n\n"
        "**Notifications:**\n"
        "`/notify on/off` - Toggle alerts\n"
        "`/notifyinterval [num]` - Alert frequency\n\n"
        "**System:**\n"
        "`/health` - Bot health\n"
        "`/logs` - View logs\n"
        "`/menu` - Show buttons",
        buttons=get_main_menu()
    )

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
            f"✅ **Forwarding Complete!**\n\n"
            f"📊 Total: {forwarded} messages\n"
            f"🔄 Last ID: {config['last_forwarded_id']}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"Use `/forward` to continue",
            buttons=get_main_menu()
        )
    except Exception as e:
        logger.error(f"❌ Task error: {e}")
        await client.send_message(
            ADMIN_ID,
            f"❌ **Error:**\n`{str(e)}`\n\n"
            f"Last ID: {config['last_forwarded_id']}\n"
            f"Use `/setid {config['last_forwarded_id']}` to resume",
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
            
            # Send as new message (NO FORWARD TAG)
            await client.send_message(
                dest,
                event.message.text if event.message.text else "",
                file=event.message.media if event.message.media else None,
                formatting_entities=event.message.entities
            )
            
            config['forwarded_count'] += 1
            config['last_forwarded_id'] = event.message.id
            
            # Notify every N messages
            if config.get('notify_batch', True) and config['forwarded_count'] % config.get('notify_interval', 50) == 0:
                await client.send_message(
                    ADMIN_ID,
                    f"🤖 **Auto-Forward Update**\n\n"
                    f"✅ Total: {config['forwarded_count']}\n"
                    f"🔄 Last ID: {event.message.id}"
                )
            
            save_config(config)
            logger.info(f"✅ Auto-forwarded: {event.message.id}")
    except Exception as e:
        logger.error(f"Auto-forward error: {e}")

# ============================================
# MAIN
# ============================================
async def main():
    logger.info("=" * 50)
    logger.info("🚀 Telegram Userbot Starting...")
    logger.info("🆔 Channel ID-based Forwarding")
    logger.info("🖥️ Optimized for Ubuntu & Render")
    logger.info("=" * 50)
    
    # Validate environment
    if not validate_env():
        logger.error("❌ Please set environment variables and restart")
        return
    
    try:
        # START HTTP SERVER FIRST (CRITICAL FOR RENDER!)
        logger.info(f"🌐 Starting HTTP server on 0.0.0.0:{PORT}...")
        http_runner = await start_http_server()
        logger.info(f"✅ HTTP server running on port {PORT}")
        logger.info(f"🔗 Health check: http://0.0.0.0:{PORT}/health")
        
        # Then connect to Telegram
        logger.info("📱 Connecting to Telegram...")
        await client.connect()
        
        # Check if authorized
        if not await client.is_user_authorized():
            logger.error("❌ Not authorized!")
            logger.error("=" * 50)
            logger.error("⚠️ You need to generate a session first!")
            logger.error("")
            logger.error("📋 Steps to fix:")
            logger.error("1. Run string_session_generator.py locally")
            logger.error("2. Copy the session string")
            logger.error("3. Add to Render env: SESSION_STRING=your_string")
            logger.error("=" * 50)
            return
        
        me = await client.get_me()
        logger.info(f"✅ Connected as: {me.first_name}")
        logger.info(f"📋 User ID: {me.id}")
        logger.info(f"📱 Phone: {me.phone}")
        logger.info("=" * 50)
        
        # Start keep-alive task
        asyncio.create_task(keep_alive_task())
        logger.info("💓 Keep-alive task started")
        
        # Send startup notification
        await client.send_message(
            ADMIN_ID,
            "🤖 **Userbot Started Successfully!**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🆔 Channel ID-based Forwarding\n"
            f"🖥️ Running on Render (Port {PORT})\n"
            "🌐 HTTP server active\n\n"
            "**Quick Start:**\n"
            "1. `/source [channel_id]`\n"
            "2. `/dest [channel_id]`\n"
            "3. `/forward`\n\n"
            "Send /start for full menu\n"
            "Send /help for all commands",
            buttons=[[Button.inline("📋 Open Menu", b"refresh")]]
        )
        
        logger.info("✅ Bot is ready and waiting for commands!")
        logger.info("📋 Send /start to begin")
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
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise
