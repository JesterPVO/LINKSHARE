import asyncio
import logging
import sqlite3
import re
import time
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ChatMemberStatus

# ================= CONFIGURATION =================
BOT_TOKEN = "8876529386:AAEXwQUSUv6QBmMPP_YtavhyaY_Jb4GomZ4"
ADMIN_PASS = "ahadop123"

# ================= DATABASE SETUP =================
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()

# Tables setup
cursor.execute('''CREATE TABLE IF NOT EXISTS message_counts (
                    user_id INTEGER, 
                    chat_id INTEGER, 
                    username TEXT, 
                    count INTEGER DEFAULT 0, 
                    PRIMARY KEY (user_id, chat_id))''')

cursor.execute('''CREATE TABLE IF NOT EXISTS user_names (
                    user_id INTEGER PRIMARY KEY, 
                    name TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, 
                    value TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS custom_commands (
                    command TEXT PRIMARY KEY, 
                    response TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS sent_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    username TEXT,
                    link TEXT,
                    timestamp REAL)''')

# Initial Default Settings
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('start_msg', 'Hello! Welcome to our Bot.')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_msg', 'Welcome to the group!')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('help_msg', 'Here are the available commands: /start, /ranking, /synclinks, /setmyname, /help')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('force_sub', '')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('buttons', 'Google|https://google.com')")
conn.commit()

# Helper Functions
def get_setting(key):
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = cursor.fetchone()
    return res[0] if res else ""

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

# Rank Tier Calculator
def get_rank_title(count):
    if count >= 500:
        return "👑 Master"
    elif count >= 300:
        return "💎 Diamond"
    elif count >= 150:
        return "🥇 Gold"
    elif count >= 50:
        return "🥈 Silver"
    else:
        return "🥉 Bronze"

# ================= BOT INITIALIZATION =================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================= FORCE SUB MIDDLEWARE =================
async def check_force_sub(user_id: int) -> bool:
    channel = get_setting("force_sub")
    if not channel or not channel.startswith("@"):
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status not in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]
    except Exception:
        return True

# ================= HANDLERS =================

# --- /start Command ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    
    if not await check_force_sub(user_id):
        channel = get_setting("force_sub")
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📢 Join Channel", url=f"https://t.me/{channel.replace('@', '')}")
        ]])
        await message.answer(f"❌ You must join {channel} to use this bot!", reply_markup=kb)
        return

    raw_buttons = get_setting("buttons")
    keyboard = []
    if raw_buttons:
        for item in raw_buttons.split(","):
            if "|" in item:
                title, url = item.split("|")
                keyboard.append([InlineKeyboardButton(text=title.strip(), url=url.strip())])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
    await message.answer(get_setting("start_msg"), reply_markup=markup)

# --- /help Command ---
@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    default_help = (
        "🤖 **Bot Command Guide** 🤖\n\n"
        "• `/start` — Start the bot & show buttons\n"
        "• `/help` — Show this help message\n"
        "• `/ranking` or `/top` — View top 10 chat leaderboard & ranks\n"
        "• `/synclinks` — View collected links (Today, Yesterday, Weekly)\n"
        "• `/setmyname <name>` — Set your custom display name for rankings\n"
    )
    custom_help = get_setting("help_msg")
    await message.answer(f"{default_help}\n{custom_help}", parse_mode="Markdown")

# --- Set Custom Display Name Command ---
@dp.message(Command("setmyname"))
async def set_my_name(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("Usage: `/setmyname YourCustomName`", parse_mode="Markdown")
        return
    
    custom_name = command.args.strip()
    user_id = message.from_user.id
    
    cursor.execute("INSERT OR REPLACE INTO user_names (user_id, name) VALUES (?, ?)", (user_id, custom_name))
    conn.commit()
    
    await message.answer(f"✅ Your leaderboard display name has been set to: **{custom_name}**", parse_mode="Markdown")

# --- Leaderboard & Tier Rank System ---
@dp.message(Command("ranking", "top"))
async def ranking_cmd(message: types.Message):
    if message.chat.type == "private":
        await message.answer("ℹ️ Use this command in a group to view the chatter leaderboard.")
        return

    cursor.execute(
        """SELECT m.username, m.count, u.name 
           FROM message_counts m 
           LEFT JOIN user_names u ON m.user_id = u.user_id 
           WHERE m.chat_id=? 
           ORDER BY m.count DESC LIMIT 10""", 
        (message.chat.id,)
    )
    top_chatters = cursor.fetchall()
    
    if not top_chatters:
        await message.answer("📊 No chat activity recorded yet.")
        return

    leaderboard = "🏆 **Top 10 Chatter Leaderboard & Ranks** 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"] + ["👤"] * 7
    
    for idx, (username, count, custom_name) in enumerate(top_chatters):
        display_name = custom_name if custom_name else (f"@{username}" if username else f"User_{idx+1}")
        rank_title = get_rank_title(count)
        leaderboard += f"{medals[idx]} **{idx+1}. {display_name}** — `{count}` msgs | *Rank: {rank_title}*\n"

    await message.answer(leaderboard, parse_mode="Markdown")

# --- Sync Links Command ---
@dp.message(Command("synclinks"))
async def synclinks_cmd(message: types.Message):
    if message.chat.type == "private":
        await message.answer("ℹ️ Use this command in a group to view synced links.")
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Today", callback_data="links_today"),
            InlineKeyboardButton(text="📆 Yesterday", callback_data="links_yesterday")
        ],
        [
            InlineKeyboardButton(text="📊 Weekly", callback_data="links_weekly")
        ]
    ])
    await message.answer("🔗 **Link Sync Center**\nSelect a timeframe below to view collected links with time details:", reply_markup=kb, parse_mode="Markdown")

# --- Link Timeframe Callback Query Handler with Timestamps ---
@dp.callback_query(F.data.startswith("links_"))
async def links_callback(callback: types.CallbackQuery):
    action = callback.data.split("_")[1]
    chat_id = callback.message.chat.id
    now = datetime.now()
    
    if action == "today":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        cursor.execute(
            "SELECT username, link, timestamp FROM sent_links WHERE chat_id=? AND timestamp >= ? ORDER BY timestamp DESC LIMIT 15",
            (chat_id, start_time)
        )
        title = "Today's"
    elif action == "yesterday":
        yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        cursor.execute(
            "SELECT username, link, timestamp FROM sent_links WHERE chat_id=? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp DESC LIMIT 15",
            (chat_id, yesterday_start, today_start)
        )
        title = "Yesterday's"
    elif action == "weekly":
        start_time = (now - timedelta(days=7)).timestamp()
        cursor.execute(
            "SELECT username, link, timestamp FROM sent_links WHERE chat_id=? AND timestamp >= ? ORDER BY timestamp DESC LIMIT 15",
            (chat_id, start_time)
        )
        title = "Past 7 Days'"
    else:
        return

    rows = cursor.fetchall()
    if not rows:
        await callback.answer(f"No links found for {title.lower()}!", show_alert=True)
        return
    
    response_text = f"🔗 **{title} Links & Sent Time:**\n\n"
    for idx, (username, link, timestamp) in enumerate(rows, 1):
        name = f"@{username}" if username else "User"
        time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        response_text += f"{idx}. **{name}** at `{time_str}`:\n{link}\n\n"
    
    if len(response_text) > 4096:
        response_text = response_text[:4093] + "..."
        
    await callback.message.edit_text(response_text, parse_mode="Markdown", disable_web_page_preview=True)
    await callback.answer()

# ================= MODERATION COMMANDS (Mute / Ban) =================
@dp.message(Command("ban"))
async def ban_user(message: types.Message):
    if message.chat.type == "private":
        return
    # Check if user is admin/creator
    member = await message.chat.get_member(message.from_user.id)
    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
        await message.answer("❌ You must be an admin to use `/ban`.")
        return
    
    if not message.reply_to_message:
        await message.answer("⚠️ Reply to the user you want to ban.")
        return
    
    target_id = message.reply_to_message.from_user.id
    try:
        await message.chat.ban(user_id=target_id)
        await message.answer(f"🔨 User has been banned successfully.")
    except Exception as e:
        await message.answer(f"❌ Failed to ban user: {e}")

@dp.message(Command("mute"))
async def mute_user(message: types.Message):
    if message.chat.type == "private":
        return
    member = await message.chat.get_member(message.from_user.id)
    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
        await message.answer("❌ You must be an admin to use `/mute`.")
        return
    
    if not message.reply_to_message:
        await message.answer("⚠️ Reply to the user you want to mute.")
        return
    
    target_id = message.reply_to_message.from_user.id
    try:
        # Restrict user from sending messages
        await message.chat.restrict(
            user_id=target_id,
            permissions=types.ChatPermissions(can_send_messages=False)
        )
        await message.answer(f"🔇 User has been muted.")
    except Exception as e:
        await message.answer(f"❌ Failed to mute user: {e}")

# ================= SECRET ADMIN PANEL =================
@dp.message(Command("admin"))
async def admin_cmd(message: types.Message, command: CommandObject):
    if command.args != ADMIN_PASS:
        await message.answer("❌ Access Denied: Incorrect Password!")
        return

    admin_text = (
        "⚙️ **Easy Admin Control Panel** ⚙️\n\n"
        "• `/setstart <text>` — Edit Start Message\n"
        "• `/setwelcome <text>` — Edit Group Welcome Message\n"
        "• `/sethelp <text>` — Edit Help Command Popup Content\n"
        "• `/setforcesub <@channel>` — Set Force Join Channel (`none` to disable)\n"
        "• `/setbuttons <Label|URL, Label2|URL2>` — Edit Start Inline Buttons\n"
        "• `/addcmd </cmd> <response>` — Add custom command\n"
        "• `/delcmd </cmd>` — Delete custom command"
    )
    await message.answer(admin_text, parse_mode="Markdown")

# --- Easy Admin Setters ---
@dp.message(Command("setstart"))
async def set_start_msg(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("Usage: `/setstart Your welcome text here`", parse_mode="Markdown")
        return
    set_setting("start_msg", command.args)
    await message.answer("✅ Start message updated!")

@dp.message(Command("setwelcome"))
async def set_welcome_msg(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("Usage: `/setwelcome Hello! Welcome to the group.`", parse_mode="Markdown")
        return
    set_setting("welcome_msg", command.args)
    await message.answer("✅ Group welcome message updated!")

@dp.message(Command("sethelp"))
async def set_help_msg(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("Usage: `/sethelp Your custom extra help text here`", parse_mode="Markdown")
        return
    set_setting("help_msg", command.args)
    await message.answer("✅ Help text updated!")

@dp.message(Command("setforcesub"))
async def set_force_sub_cmd(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("Usage: `/setforcesub @ChannelUsername` or `/setforcesub none`", parse_mode="Markdown")
        return
    val = "" if command.args.lower() == "none" else command.args
    set_setting("force_sub", val)
    await message.answer(f"✅ Force Sub set to: `{val or 'Disabled'}`", parse_mode="Markdown")

@dp.message(Command("setbuttons"))
async def set_buttons_cmd(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("Usage: `/setbuttons Google|https://google.com, Support|https://t.me/admin`", parse_mode="Markdown")
        return
    set_setting("buttons", command.args)
    await message.answer("✅ Start Inline buttons updated!")

@dp.message(Command("addcmd"))
async def add_custom_cmd(message: types.Message, command: CommandObject):
    if not command.args or len(command.args.split(maxsplit=1)) < 2:
        await message.answer("Usage: `/addcmd /rule Always be respectful!`", parse_mode="Markdown")
        return
    cmd_name, response = command.args.split(maxsplit=1)
    if not cmd_name.startswith("/"):
        cmd_name = f"/{cmd_name}"
    
    cursor.execute("INSERT OR REPLACE INTO custom_commands (command, response) VALUES (?, ?)", (cmd_name, response))
    conn.commit()
    await message.answer(f"✅ Custom command `{cmd_name}` saved!", parse_mode="Markdown")

@dp.message(Command("delcmd"))
async def del_custom_cmd(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("Usage: `/delcmd /rule`", parse_mode="Markdown")
        return
    cmd_name = command.args.strip()
    cursor.execute("DELETE FROM custom_commands WHERE command=?", (cmd_name,))
    conn.commit()
    await message.answer(f"✅ Custom command `{cmd_name}` removed!", parse_mode="Markdown")

# ================= GENERAL MESSAGE & WELCOME HANDLER =================
@dp.message()
async def process_messages(message: types.Message):
    # 1. Welcome New Members Handler
    if message.new_chat_members:
        welcome_text = get_setting("welcome_msg")
        for new_user in message.new_chat_members:
            await message.answer(f"Hello @{new_user.username or new_user.first_name}! {welcome_text}")
        return

    # 2. Custom Command Processing
    if message.text and message.text.startswith("/"):
        cmd = message.text.split()[0]
        cursor.execute("SELECT response FROM custom_commands WHERE command=?", (cmd,))
        row = cursor.fetchone()
        if row:
            await message.answer(row[0])
            return

    # 3. Chat Activity Tracker & Link Logger (Groups & Supergroups)
    if message.chat.type in ["group", "supergroup"]:
        user_id = message.from_user.id
        chat_id = message.chat.id
        username = message.from_user.username or message.from_user.first_name

        # Increment message/activity count
        cursor.execute(
            "INSERT INTO message_counts (user_id, chat_id, username, count) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(user_id, chat_id) DO UPDATE SET count = count + 1, username = excluded.username",
            (user_id, chat_id, username)
        )

        # Detect and log any links sent in message text or caption
        text = message.text or message.caption or ""
        urls = re.findall(r'(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s]*)', text)
        if urls:
            current_time = time.time()
            for url in urls:
                cursor.execute(
                    "INSERT INTO sent_links (chat_id, username, link, timestamp) VALUES (?, ?, ?, ?)",
                    (chat_id, username, url, current_time)
                )

        conn.commit()

# ================= RUN BOT =================
async def main():
    print("🤖 Bot is starting up...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
