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
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================= CONFIGURATION =================
BOT_TOKEN = "8876529386:AAEXwQUSUv6QBmMPP_YtavhyaY_Jb4GomZ4"
ADMIN_PASS = "ahadop123"

# ================= DATABASE SETUP =================
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS message_counts (
                    user_id INTEGER, 
                    chat_id INTEGER, 
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
                    user_id INTEGER,
                    link TEXT,
                    timestamp REAL)''')

# Initial Default Settings
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('start_msg', '🎭 Welcome to the Anonymous Chat Bot!')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_msg', 'Welcome to the anonymous group! Your real profile is protected.')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('help_msg', 'Commands: /start, /ranking, /synclinks, /setmyname, /help')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('force_sub', '')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('buttons', 'Google|https://google.com')")
conn.commit()

# FSM States for Admin Panel Inputs
class AdminStates(StatesGroup):
    waiting_start_msg = State()
    waiting_welcome_msg = State()
    waiting_help_msg = State()
    waiting_forcesub = State()
    waiting_buttons = State()
    waiting_addcmd = State()
    waiting_delcmd = State()

# Helper Functions
def get_setting(key):
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = cursor.fetchone()
    return res[0] if res else ""

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

def get_anon_name(user_id):
    cursor.execute("SELECT name FROM user_names WHERE user_id=?", (user_id,))
    res = cursor.fetchone()
    if res and res[0]:
        return f"🎭 {res[0]}"
    short_id = str(user_id)[-4:]
    return f"🕵️ Anon_{short_id}"

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

def get_admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Edit Start Msg", callback_data="admin_edit_start"),
            InlineKeyboardButton(text="✏️ Edit Welcome Msg", callback_data="admin_edit_welcome")
        ],
        [
            InlineKeyboardButton(text="✏️ Edit Help Msg", callback_data="admin_edit_help"),
            InlineKeyboardButton(text="📢 Edit Force Sub", callback_data="admin_edit_forcesub")
        ],
        [
            InlineKeyboardButton(text="🔘 Edit Start Buttons", callback_data="admin_edit_buttons")
        ],
        [
            InlineKeyboardButton(text="➕ Add Command", callback_data="admin_add_cmd"),
            InlineKeyboardButton(text="➖ Delete Command", callback_data="admin_del_cmd")
        ]
    ])

# ================= BOT INITIALIZATION =================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================= FORCE SUB CHECK =================
async def check_force_sub(user_id: int) -> bool:
    channel = get_setting("force_sub")
    if not channel or not channel.startswith("@"):
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status not in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]
    except Exception:
        return True

# ================= USER HANDLERS =================

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
        "🎭 **Anonymous Chat Bot Guide** 🎭\n\n"
        "• `/start` — Start bot and view buttons\n"
        "• `/help` — Show command guide\n"
        "• `/ranking` or `/top` — View top anonymous chatters & ranks\n"
        "• `/synclinks` — View shared links with timestamps\n"
        "• `/setmyname <alias>` — Set custom anonymous alias\n"
    )
    custom_help = get_setting("help_msg")
    await message.answer(f"{default_help}\n{custom_help}", parse_mode="Markdown")

# --- Set Anonymous Alias Command ---
@dp.message(Command("setmyname"))
async def set_my_name(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("Usage: `/setmyname ShadowUser`", parse_mode="Markdown")
        return
    
    custom_name = command.args.strip()
    user_id = message.from_user.id
    
    cursor.execute("INSERT OR REPLACE INTO user_names (user_id, name) VALUES (?, ?)", (user_id, custom_name))
    conn.commit()
    
    await message.answer(f"✅ Your anonymous alias is now set to: **🎭 {custom_name}**", parse_mode="Markdown")

# --- Anonymous Leaderboard (Rank Alias ke Saamne) ---
@dp.message(Command("ranking", "top"))
async def ranking_cmd(message: types.Message):
    if message.chat.type == "private":
        await message.answer("ℹ️ Use this command in a group to view chatter rankings.")
        return

    cursor.execute(
        """SELECT m.user_id, m.count 
           FROM message_counts m 
           WHERE m.chat_id=? 
           ORDER BY m.count DESC LIMIT 10""", 
        (message.chat.id,)
    )
    top_chatters = cursor.fetchall()
    
    if not top_chatters:
        await message.answer("📊 No activity recorded yet.")
        return

    leaderboard = "🏆 **Top 10 Active Members Leaderboard** 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"] + ["👤"] * 7
    
    for idx, (user_id, count) in enumerate(top_chatters):
        display_name = get_anon_name(user_id)
        rank_title = get_rank_title(count)
        # Rank formatted directly in front of the Alias
        leaderboard += f"{medals[idx]} **{idx+1}. {display_name}** `[{rank_title}]` — `{count}` msgs\n"

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
    await message.answer("🔗 **Anonymous Link Sync Center**\nSelect timeframe to view shared links:", reply_markup=kb, parse_mode="Markdown")

# --- Link Callback Handler ---
@dp.callback_query(F.data.startswith("links_"))
async def links_callback(callback: types.CallbackQuery):
    action = callback.data.split("_")[1]
    chat_id = callback.message.chat.id
    now = datetime.now()
    
    if action == "today":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        cursor.execute(
            "SELECT user_id, link, timestamp FROM sent_links WHERE chat_id=? AND timestamp >= ? ORDER BY timestamp DESC LIMIT 15",
            (chat_id, start_time)
        )
        title = "Today's"
    elif action == "yesterday":
        yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        cursor.execute(
            "SELECT user_id, link, timestamp FROM sent_links WHERE chat_id=? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp DESC LIMIT 15",
            (chat_id, yesterday_start, today_start)
        )
        title = "Yesterday's"
    elif action == "weekly":
        start_time = (now - timedelta(days=7)).timestamp()
        cursor.execute(
            "SELECT user_id, link, timestamp FROM sent_links WHERE chat_id=? AND timestamp >= ? ORDER BY timestamp DESC LIMIT 15",
            (chat_id, start_time)
        )
        title = "Past 7 Days'"
    else:
        return

    rows = cursor.fetchall()
    if not rows:
        await callback.answer(f"No links found for {title.lower()}!", show_alert=True)
        return
    
    response_text = f"🔗 **{title} Shared Links:**\n\n"
    for idx, (user_id, link, timestamp) in enumerate(rows, 1):
        anon_name = get_anon_name(user_id)
        time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        response_text += f"{idx}. **{anon_name}** at `{time_str}`:\n{link}\n\n"
    
    if len(response_text) > 4096:
        response_text = response_text[:4093] + "..."
        
    await callback.message.edit_text(response_text, parse_mode="Markdown", disable_web_page_preview=True)
    await callback.answer()

# ================= MODERATION COMMANDS =================
@dp.message(Command("ban"))
async def ban_user(message: types.Message):
    if message.chat.type == "private":
        return
    member = await message.chat.get_member(message.from_user.id)
    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
        await message.answer("❌ Admin permission required.")
        return
    if not message.reply_to_message:
        await message.answer("⚠️ Reply to the target user's message.")
        return
    target_id = message.reply_to_message.from_user.id
    try:
        await message.chat.ban(user_id=target_id)
        await message.answer("🔨 User banned.")
    except Exception as e:
        await message.answer(f"❌ Ban failed: {e}")

@dp.message(Command("mute"))
async def mute_user(message: types.Message):
    if message.chat.type == "private":
        return
    member = await message.chat.get_member(message.from_user.id)
    if member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
        await message.answer("❌ Admin permission required.")
        return
    if not message.reply_to_message:
        await message.answer("⚠️ Reply to the target user's message.")
        return
    target_id = message.reply_to_message.from_user.id
    try:
        await message.chat.restrict(
            user_id=target_id,
            permissions=types.ChatPermissions(can_send_messages=False)
        )
        await message.answer("🔇 User muted.")
    except Exception as e:
        await message.answer(f"❌ Mute failed: {e}")

# ================= INTERACTIVE INLINE ADMIN PANEL =================
@dp.message(Command("admin"))
async def admin_cmd(message: types.Message, command: CommandObject):
    if command.args != ADMIN_PASS:
        await message.answer("❌ Incorrect password.")
        return

    admin_text = (
        "⚙️ **Admin Control Panel** ⚙️\n\n"
        "Click any button below to update settings easily:"
    )
    await message.answer(admin_text, reply_markup=get_admin_panel_kb(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("admin_"))
async def admin_button_click(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data

    if action == "admin_edit_start":
        await callback.message.answer("📥 Send the new **Start Message** text:")
        await state.set_state(AdminStates.waiting_start_msg)
    elif action == "admin_edit_welcome":
        await callback.message.answer("📥 Send the new **Group Welcome Message** text:")
        await state.set_state(AdminStates.waiting_welcome_msg)
    elif action == "admin_edit_help":
        await callback.message.answer("📥 Send the new **Help Message** text:")
        await state.set_state(AdminStates.waiting_help_msg)
    elif action == "admin_edit_forcesub":
        await callback.message.answer("📥 Send the Channel Username (e.g., `@MyChannel`) or type `none` to disable:")
        await state.set_state(AdminStates.waiting_forcesub)
    elif action == "admin_edit_buttons":
        await callback.message.answer("📥 Send Inline Buttons in format:\n`Label1|URL1, Label2|URL2`", parse_mode="Markdown")
        await state.set_state(AdminStates.waiting_buttons)
    elif action == "admin_add_cmd":
        await callback.message.answer("📥 Send command and response in format:\n`/cmdname Reply text here`", parse_mode="Markdown")
        await state.set_state(AdminStates.waiting_addcmd)
    elif action == "admin_del_cmd":
        await callback.message.answer("📥 Send the command name to delete (e.g., `/cmdname`):", parse_mode="Markdown")
        await state.set_state(AdminStates.waiting_delcmd)

    await callback.answer()

# --- State Input Processors ---
@dp.message(AdminStates.waiting_start_msg)
async def process_set_start(message: types.Message, state: FSMContext):
    set_setting("start_msg", message.text)
    await message.answer("✅ **Start Message updated!**", reply_markup=get_admin_panel_kb(), parse_mode="Markdown")
    await state.clear()

@dp.message(AdminStates.waiting_welcome_msg)
async def process_set_welcome(message: types.Message, state: FSMContext):
    set_setting("welcome_msg", message.text)
    await message.answer("✅ **Welcome Message updated!**", reply_markup=get_admin_panel_kb(), parse_mode="Markdown")
    await state.clear()

@dp.message(AdminStates.waiting_help_msg)
async def process_set_help(message: types.Message, state: FSMContext):
    set_setting("help_msg", message.text)
    await message.answer("✅ **Help Message updated!**", reply_markup=get_admin_panel_kb(), parse_mode="Markdown")
    await state.clear()

@dp.message(AdminStates.waiting_forcesub)
async def process_set_forcesub(message: types.Message, state: FSMContext):
    val = "" if message.text.lower() == "none" else message.text
    set_setting("force_sub", val)
    await message.answer(f"✅ **Force Sub set to:** `{val or 'Disabled'}`", reply_markup=get_admin_panel_kb(), parse_mode="Markdown")
    await state.clear()

@dp.message(AdminStates.waiting_buttons)
async def process_set_buttons(message: types.Message, state: FSMContext):
    set_setting("buttons", message.text)
    await message.answer("✅ **Start Buttons updated!**", reply_markup=get_admin_panel_kb(), parse_mode="Markdown")
    await state.clear()

@dp.message(AdminStates.waiting_addcmd)
async def process_add_cmd(message: types.Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Invalid format! Please send `/cmdname response_text`.")
        return
    cmd_name, response = parts[0], parts[1]
    if not cmd_name.startswith("/"):
        cmd_name = f"/{cmd_name}"
    cursor.execute("INSERT OR REPLACE INTO custom_commands (command, response) VALUES (?, ?)", (cmd_name, response))
    conn.commit()
    await message.answer(f"✅ **Custom command `{cmd_name}` saved!**", reply_markup=get_admin_panel_kb(), parse_mode="Markdown")
    await state.clear()

@dp.message(AdminStates.waiting_delcmd)
async def process_del_cmd(message: types.Message, state: FSMContext):
    cmd_name = message.text.strip()
    if not cmd_name.startswith("/"):
        cmd_name = f"/{cmd_name}"
    cursor.execute("DELETE FROM custom_commands WHERE command=?", (cmd_name,))
    conn.commit()
    await message.answer(f"✅ **Command `{cmd_name}` removed!**", reply_markup=get_admin_panel_kb(), parse_mode="Markdown")
    await state.clear()

# ================= MESSAGES & TRACKING =================
@dp.message()
async def process_messages(message: types.Message):
    if message.new_chat_members:
        welcome_text = get_setting("welcome_msg")
        await message.answer(f"🎭 Welcome to the chat! {welcome_text}")
        return

    if message.text and message.text.startswith("/"):
        cmd = message.text.split()[0]
        cursor.execute("SELECT response FROM custom_commands WHERE command=?", (cmd,))
        row = cursor.fetchone()
        if row:
            await message.answer(row[0])
            return

    if message.chat.type in ["group", "supergroup"]:
        user_id = message.from_user.id
        chat_id = message.chat.id

        cursor.execute(
            "INSERT INTO message_counts (user_id, chat_id, count) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, chat_id) DO UPDATE SET count = count + 1",
            (user_id, chat_id)
        )

        text = message.text or message.caption or ""
        urls = re.findall(r'(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s]*)', text)
        if urls:
            current_time = time.time()
            for url in urls:
                cursor.execute(
                    "INSERT INTO sent_links (chat_id, user_id, link, timestamp) VALUES (?, ?, ?, ?)",
                    (chat_id, user_id, url, current_time)
                )

        conn.commit()

# ================= RUN BOT =================
async def main():
    print("🤖 Anonymous Chat Bot started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
