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
BOT_TOKEN = "8933523782:AAFahGIoE2J5BUfelAM7NhwnCdtRhlLD9X0"
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
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('force_sub', '')")  # e.g., @MyChannel
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
    
    # Check Force Sub
    if not await check_force_sub(user_id):
        channel = get_setting("force_sub")
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📢 Join Channel", url=f"https://t.me/{channel.replace('@', '')}")
        ]])
        await message.answer(f"❌ You must join {channel} to use this bot!", reply_markup=kb)
        return

    # Fetch custom buttons
    raw_buttons = get_setting("buttons")
    keyboard = []
    if raw_buttons:
        for item in raw_buttons.split(","):
            if "|" in item:
                title, url = item.split("|")
                keyboard.append([InlineKeyboardButton(text=title.strip(), url=url.strip())])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
    await message.answer(get_setting("start_msg"), reply_markup=markup)

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

# --- Leaderboard / Ranking Command ---
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

    leaderboard = "🏆 **Top 10 Most Active Chatters** 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"] + ["👤"] * 7
    
    for idx, (username, count, custom_name) in enumerate(top_chatters):
        display_name = custom_name if custom_name else (f"@{username}" if username else f"User_{idx+1}")
        leaderboard += f"{medals[idx]} **{idx+1}. {display_name}** — `{count}` messages/activities\n"

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
    await message.answer("🔗 **Link Sync Center**\nSelect a timeframe below to view collected links:", reply_markup=kb, parse_mode="Markdown")

# --- Link Timeframe Callback Query Handler ---
@dp.callback_query(F.data.startswith("links_"))
async def links_callback(callback: types.CallbackQuery):
    action = callback.data.split("_")[1]
    chat_id = callback.message.chat.id
    now = datetime.now()
    
    if action == "today":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        cursor.execute(
            "SELECT username, link FROM sent_links WHERE chat_id=? AND timestamp >= ? ORDER BY timestamp DESC LIMIT 20",
            (chat_id, start_time)
        )
        title = "Today's"
    elif action == "yesterday":
        yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        cursor.execute(
            "SELECT username, link FROM sent_links WHERE chat_id=? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp DESC LIMIT 20",
            (chat_id, yesterday_start, today_start)
        )
        title = "Yesterday's"
    elif action == "weekly":
        start_time = (now - timedelta(days=7)).timestamp()
        cursor.execute(
            "SELECT username, link FROM sent_links WHERE chat_id=? AND timestamp >= ? ORDER BY timestamp DESC LIMIT 20",
            (chat_id, start_time)
        )
        title = "Past 7 Days'"
    else:
        return

    rows = cursor.fetchall()
    if not rows:
        await callback.answer(f"No links found for {title.lower()}!", show_alert=True)
        return
    
    response_text = f"🔗 **{title} Links Collected:**\n\n"
    for idx, (username, link) in enumerate(rows, 1):
        name = f"@{username}" if username else "User"
        response_text += f"{idx}. {name}: {link}\n"
    
    if len(response_text) > 4096:
        response_text = response_text[:4093] + "..."
        
    await callback.message.edit_text(response_text, parse_mode="Markdown", disable_web_page_preview=True)
    await callback.answer()

# --- Secret Admin Panel Command (/admin ahadop123) ---
@dp.message(Command("admin"))
async def admin_cmd(message: types.Message, command: CommandObject):
    if command.args != ADMIN_PASS:
        await message.answer("❌ Access Denied: Incorrect Password!")
        return

    admin_text = (
        "⚙️ **Admin Control Panel** ⚙️\n\n"
        "**Available Commands:**\n"
        "• `/setstart <text>` — Update Start Message\n"
        "• `/setforcesub <@channel>` — Set Force Join Channel (use `none` to disable)\n"
        "• `/setbuttons <Label1|URL1, Label2|URL2>` — Configure Inline Buttons\n"
        "• `/addcmd </cmdname> <reply text>` — Create Custom Command (e.g., `/addcmd /help Need support?`)\n"
        "• `/delcmd </cmdname>` — Delete Custom Command"
    )
    await message.answer(admin_text, parse_mode="Markdown")

# --- Admin Configuration Commands ---
@dp.message(Command("setstart"))
async def set_start_msg(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("Usage: `/setstart Your welcome text here`", parse_mode="Markdown")
        return
    set_setting("start_msg", command.args)
    await message.answer("✅ Start message updated!")

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
        await message.answer("Usage: `/addcmd /help Here is the help text!`", parse_mode="Markdown")
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
        await message.answer("Usage: `/delcmd /help`", parse_mode="Markdown")
        return
    cmd_name = command.args.strip()
    cursor.execute("DELETE FROM custom_commands WHERE command=?", (cmd_name,))
    conn.commit()
    await message.answer(f"✅ Custom command `{cmd_name}` removed!", parse_mode="Markdown")

# --- Group Message Tracking & Link Extraction Handler ---
@dp.message()
async def process_messages(message: types.Message):
    # 1. Custom Command Processing
    if message.text and message.text.startswith("/"):
        cmd = message.text.split()[0]
        cursor.execute("SELECT response FROM custom_commands WHERE command=?", (cmd,))
        row = cursor.fetchone()
        if row:
            await message.answer(row[0])
            return

    # 2. Chat Activity Tracker & Link Logger (Groups & Supergroups)
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
