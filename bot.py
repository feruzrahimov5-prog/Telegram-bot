import asyncio
import logging
import random
import aiohttp
import sqlite3
import re
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ==================== SOZLAMALAR ====================
logging.basicConfig(level=logging.INFO)

TOKEN = "8869897716:AAG13rX0nbq3DKvpVx7ZrAHa2zx-Xy9xhd0"
ADMIN_ID = 1829563275
API_KEY = "51c9fcdaecf3a239cdf85aaeddd098e273b208e505edf2f66d94d3efee562751"

api_id = 35651244
api_hash = "d7283bdd8484f650890dba335104f969"
phone = "+998919162323"
SESSION_STRING = os.getenv("USERBOT_SESSION", "")

DEPOSIT_URL = "https://api.1win.win/v1/client/deposit"

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

CARDS = ["9860 3501 4449 2351", "9860 2466 0248 6556"]
card_index = 0

def get_next_card():
    global card_index
    card = CARDS[card_index]
    card_index = (card_index + 1) % len(CARDS)
    return card

def generate_random_amount(amount):
    """Random summa yaratish (BUTUN SON)"""
    change = random.uniform(0.1, 0.5)
    if random.choice([True, False]):
        return int(round(amount * (1 + change / 100)))
    return int(round(amount * (1 - change / 100)))

class DepositState(StatesGroup):
    waiting_id = State()
    waiting_confirm = State()
    waiting_amount = State()

class WithdrawState(StatesGroup):
    waiting_id = State()
    waiting_card = State()
    waiting_code = State()

class AdminWithdrawState(StatesGroup):
    waiting_amount = State()

# ==================== DATABASE ====================
DB_PATH = "users.db"
PENDING_DB = "pending.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT, joined_date TEXT)''')
    conn.commit()
    conn.close()

def init_pending_db():
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS pending_deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id_1win TEXT, telegram_id TEXT, amount REAL, random_amount REAL, card_number TEXT, status TEXT, created_at TEXT)''')
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name, last_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined_date) VALUES (?, ?, ?, ?, datetime('now'))''', (user_id, username, first_name, last_name))
    conn.commit()
    conn.close()

def get_total_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def add_pending_deposit(user_id_1win, telegram_id, amount, random_amount, card_number):
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO pending_deposits (user_id_1win, telegram_id, amount, random_amount, card_number, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', datetime('now'))''', (user_id_1win, telegram_id, amount, random_amount, card_number))
    conn.commit()
    conn.close()

def get_pending_deposit_by_amount(incoming_amount):
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute('''SELECT id, user_id_1win, telegram_id, amount, random_amount, card_number FROM pending_deposits WHERE status = 'pending' AND CAST(ROUND(random_amount) AS INTEGER) = ? ORDER BY created_at DESC LIMIT 1''', (incoming_amount,))
    row = cursor.fetchone()
    if not row:
        cursor.execute('''SELECT id, user_id_1win, telegram_id, amount, random_amount, card_number FROM pending_deposits WHERE status = 'pending' AND CAST(ROUND(random_amount) AS INTEGER) BETWEEN ? AND ? ORDER BY created_at DESC LIMIT 1''', (incoming_amount - 3, incoming_amount + 3))
        row = cursor.fetchone()
    conn.close()
    return row

def update_deposit_status(deposit_id, status):
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute('UPDATE pending_deposits SET status = ? WHERE id = ?', (status, deposit_id))
    conn.commit()
    conn.close()

def get_pending_deposits_count():
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pending_deposits WHERE status = 'pending'")
    count = cursor.fetchone()[0]
    conn.close()
    return count

init_db()
init_pending_db()

# ==================== MENYU ====================
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💎 HISOB TO'LDIRISH")],
        [KeyboardButton(text="💸 PUL YECHISH")],
        [KeyboardButton(text="🌐 1WIN SAYTI")],
        [KeyboardButton(text="📞 ADMIN BILAN BOG'LANISH")]
    ],
    resize_keyboard=True
)

async def send_deposit_to_1win(user_id: str, amount: int):
    try:
        headers = {"X-API-KEY": API_KEY, "Content-Type": "application/json"}
        payload = {"userId": int(user_id), "amount": amount}
        async with aiohttp.ClientSession() as session:
            async with session.post(DEPOSIT_URL, json=payload, headers=headers, timeout=30) as resp:
                if 200 <= resp.status < 300:
                    return {"success": True, "data": await resp.json(), "status": resp.status}
                else:
                    return {"success": False, "message": f"Status {resp.status}", "status": resp.status}
    except Exception as e:
        return {"success": False, "message": str(e), "status": 0}

# ==================== HANDLERLAR ====================
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    add_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "", message.from_user.last_name or "")
    await message.answer("🏦 **1WIN CASH**\n━━━━━━━━━━━━━━━━━━━━━\n👋 Xush kelibsiz!\n👇 Tanlang:", reply_markup=main_menu)

@dp.message(lambda message: message.text == "🌐 1WIN SAYTI")
async def website_link(message: types.Message):
    await message.answer("🌐 **1WIN SAYTI**\n👉 [Saytga o'tish](https://r1wbmjh.life/v3/aggressive-casino?p=i2ry)", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌐 SAYTGA O'TISH", url="https://r1wbmjh.life/v3/aggressive-casino?p=i2ry")]]))

@dp.message(lambda message: message.text == "📞 ADMIN BILAN BOG'LANISH")
async def admin_contact(message: types.Message):
    await message.answer("👨‍💻 **Admin:** @feruz063\n⏰ 24/7", reply_markup=main_menu)

@dp.message(lambda message: message.text == "/stats" and message.from_user.id == ADMIN_ID)
async def stats_cmd(message: types.Message):
    total = get_total_users()
    pending = get_pending_deposits_count()
    await message.answer(f"📊 **STATISTIKA**\n👥 Foydalanuvchilar: {total}\n⏳ Kutilayotgan: {pending}")

# ==================== DEPOZIT ====================
@dp.message(lambda message: message.text == "💎 HISOB TO'LDIRISH")
async def deposit_start(message: types.Message, state: FSMContext):
    await message.answer("📝 **1WIN ID** raqamingizni kiriting:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(DepositState.waiting_id)

@dp.message(DepositState.waiting_id)
async def deposit_id(message: types.Message, state: FSMContext):
    user_id = message.text.strip()
    if not user_id.isdigit():
        await message.answer("❌ ID faqat raqamlardan iborat!\n📝 Qayta kiriting:")
        return
    await state.update_data(user_id=user_id)
    await message.answer(f"👤 **1Win ID:** `{user_id}`\n✅ Bu sizning ID-ingizmi?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ HA", callback_data="confirm_id_yes")], [InlineKeyboardButton(text="❌ YO'Q", callback_data="confirm_id_no")]]))
    await state.set_state(DepositState.waiting_confirm)

@dp.callback_query(lambda c: c.data == "confirm_id_yes")
async def confirm_id_yes(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("💰 **Summani kiriting:**\n⚠️ Minimal: 20,000 so'm\nMasalan: 100000")
    await state.set_state(DepositState.waiting_amount)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "confirm_id_no")
async def confirm_id_no(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("📝 Qayta **1WIN ID** raqamingizni kiriting:")
    await state.set_state(DepositState.waiting_id)
    await callback.answer()

@dp.message(DepositState.waiting_amount)
async def deposit_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.replace(" ", ""))
        if amount < 20000:
            await message.answer("❌ Minimal: 20,000 so'm\n💰 Qayta kiriting:")
            return
        if amount > 100000000:
            await message.answer("❌ Maksimal: 100,000,000 so'm")
            return
        data = await state.get_data()
        user_id = data.get('user_id')
        random_amount = generate_random_amount(amount)
        card_number = get_next_card()
        add_pending_deposit(user_id, str(message.from_user.id), amount, random_amount, card_number)
        await state.update_data(user_amount=amount, random_amount=random_amount, card_number=card_number, user_id_1win=user_id)
        await message.answer(f"💳 **TO'LOV UCHUN:**\n\n📋 Karta: `{card_number}`\n💰 Summa: {amount:,} UZS\n🔢 O'tkaziladigan: **{random_amount:,} UZS**\n\n⚠️ Aynan shu summani o'tkazing!", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 NUSXA OLISH", callback_data=f"copy_{card_number}")], [InlineKeyboardButton(text="✅ TO'LOV QILDIM", callback_data="deposit_done")], [InlineKeyboardButton(text="❌ BEKOR QILISH", callback_data="deposit_cancel")]]))
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting!")

@dp.callback_query(lambda c: c.data.startswith('copy_'))
async def copy_card(callback: types.CallbackQuery):
    card = callback.data.split('_', 1)[1]
    await callback.answer("📋 Nusxalandi!", show_alert=True)

@dp.callback_query(lambda c: c.data == "deposit_done")
async def deposit_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id_1win = data.get('user_id_1win', '')
    random_amount = data.get('random_amount', 0)
    await callback.message.edit_text(f"⏳ **TEKSHIRILMOQDA...**\n\n💰 Summa: {random_amount:,} UZS\n\n✅ To'lov qilgan bo'lsangiz, avtomatik tasdiqlanadi.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 BOSH SAHIFA", callback_data="back_main")]]))
    await state.clear()
    await callback.answer()

@dp.callback_query(lambda c: c.data == "deposit_cancel")
async def deposit_cancel(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id_1win = data.get('user_id_1win', '')
    random_amount = data.get('random_amount', 0)
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute('''UPDATE pending_deposits SET status = 'cancelled' WHERE user_id_1win = ? AND random_amount = ? AND status = 'pending' ''', (user_id_1win, random_amount))
    conn.commit()
    conn.close()
    await callback.message.edit_text("❌ Bekor qilindi!", reply_markup=main_menu)
    await state.clear()
    await callback.answer()

# ==================== PUL YECHISH ====================
@dp.message(lambda message: message.text == "💸 PUL YECHISH")
async def withdraw_start(message: types.Message, state: FSMContext):
    await message.answer("📝 **1WIN ID** raqamingizni kiriting:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(WithdrawState.waiting_id)

@dp.message(WithdrawState.waiting_id)
async def withdraw_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ ID faqat raqamlardan iborat!\n📝 Qayta kiriting:")
        return
    await state.update_data(user_id=message.text)
    await message.answer("💳 Kartangiz raqamini kiriting (faqat raqamlar):")
    await state.set_state(WithdrawState.waiting_card)

@dp.message(WithdrawState.waiting_card)
async def withdraw_card(message: types.Message, state: FSMContext):
    card = message.text.replace(" ", "")
    if len(card) < 15 or not card.isdigit():
        await message.answer("❌ Noto'g'ri karta raqami! Qayta kiriting:")
        return
    await state.update_data(card=card)
    await message.answer("🔑 1Win dan kelgan kodni kiriting (4-10 belgi):")
    await state.set_state(WithdrawState.waiting_code)

@dp.message(WithdrawState.waiting_code)
async def withdraw_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    if len(code) < 4 or len(code) > 10:
        await message.answer("❌ Kod 4-10 belgi bo'lishi kerak!\nQayta kiriting:")
        return
    data = await state.get_data()
    user_id = data.get('user_id')
    card = data.get('card')
    await message.answer(f"✅ **Qabul qilindi!**\n📝 ID: {user_id}\n💳 Karta: {card}\n🔑 Kod: `{code}`\n\n🔔 Admin tasdiqlaydi.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 BOSH SAHIFA", callback_data="back_main")]]))
    await bot.send_message(ADMIN_ID, f"📤 **YECHIB OLISH**\n👤 @{message.from_user.username or 'NoUsername'}\n🆔 TG: {message.from_user.id}\n📝 1Win ID: {user_id}\n💳 Karta: {card}\n🔑 Kod: `{code}`", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ TASDIQLASH", callback_data=f"w_yes_{message.from_user.id}_{user_id}_{card}_{code}")], [InlineKeyboardButton(text="❌ BEKOR QILISH", callback_data=f"w_no_{message.from_user.id}")]]))
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith('w_yes_'))
async def withdraw_admin_accept(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split('_')
    user_telegram_id = int(parts[2])
    user_id_1win = parts[3]
    card = parts[4] if len(parts) > 4 else ""
    code = parts[5] if len(parts) > 5 else ""
    await callback.message.edit_text(f"📤 **SUMMANI KIRITING:**\n👤 TG: {user_telegram_id}\n📝 1Win: {user_id_1win}")
    await state.update_data(user_telegram_id=user_telegram_id, user_id_1win=user_id_1win)
    await state.set_state(AdminWithdrawState.waiting_amount)

@dp.message(AdminWithdrawState.waiting_amount)
async def admin_withdraw_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.replace(" ", ""))
        if amount < 50000:
            await message.answer("❌ Minimal yechib olish: 50,000 so'm")
            return
        if amount > 50000000:
            await message.answer("❌ Maksimal: 50,000,000 so'm")
            return
        data = await state.get_data()
        user_telegram_id = data.get('user_telegram_id')
        user_id_1win = data.get('user_id_1win')
        result = await send_deposit_to_1win(user_id_1win, amount)
        if result.get('success', False):
            await bot.send_message(user_telegram_id, f"✅ Pul yechildi!\n💰 {amount:,} UZS", reply_markup=main_menu)
            await message.answer(f"✅ {amount:,} UZS")
        else:
            error_msg = result.get('message', 'Nomaʼlum xatolik')
            await bot.send_message(user_telegram_id, f"❌ Xatolik: {error_msg}\n@feruz063")
            await message.answer(f"❌ {error_msg}")
        await state.clear()
    except ValueError:
        await message.answer("❌ Raqam kiriting!")

@dp.callback_query(lambda c: c.data.startswith('w_no_'))
async def withdraw_admin_reject(callback: types.CallbackQuery):
    user_telegram_id = int(callback.data.split('_')[2])
    await bot.send_message(user_telegram_id, "❌ Bekor qilindi.", reply_markup=main_menu)
    await callback.message.edit_text("❌ Bekor qilindi.")

@dp.callback_query(lambda c: c.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🏠 Bosh sahifa", reply_markup=main_menu)

# ==================== USERBOT (HUMO AVTOMATIK TASDIQLASH) ====================
if SESSION_STRING:
    userbot_client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash)
else:
    userbot_client = TelegramClient('userbot_session', api_id, api_hash)

@userbot_client.on(events.NewMessage(chats=['@HUMOcardbot']))
async def humo_handler(event):
    message = event.message.text
    if not message:
        return

    logging.info(f"📩 HUMO xabar: {message}")
    await bot.send_message(ADMIN_ID, f"📩 **HUMO xabar:**\n{message}")

    # ✅ HAR QANDAY FORMATDAGI SUMMANI QIDIRISH
    match = re.search(r'([\d\s.,]+)\s*UZS', message)
    if not match:
        await bot.send_message(ADMIN_ID, "❌ Summa topilmadi (UZS yo'q).")
        return

    raw = match.group(1).replace(' ', '')
    if ',' in raw and '.' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    elif ',' in raw and '.' not in raw:
        raw = raw.replace(',', '')
    elif '.' in raw and ',' not in raw:
        raw = raw.replace('.', '')

    try:
        amount = round(float(raw))
    except:
        await bot.send_message(ADMIN_ID, f"❌ Summa noto'g'ri: {raw}")
        return

    await bot.send_message(ADMIN_ID, f"💰 Aniqlangan summa: **{amount}** UZS")
    logging.info(f"💰 Aniqlangan summa: {amount} UZS")

    deposit = get_pending_deposit_by_amount(amount)
    if not deposit:
        await bot.send_message(ADMIN_ID, f"❌ {amount} UZS uchun kutilayotgan depozit topilmadi.")
        return

    dep_id, user_id_1win, tg_id, dep_amount, rand_amt, card = deposit
    await bot.send_message(ADMIN_ID, f"✅ Depozit topildi: ID {user_id_1win}, summa {dep_amount}")

    result = await send_deposit_to_1win(user_id_1win, int(dep_amount))
    if result.get("success"):
        update_deposit_status(dep_id, "success")
        try:
            await bot.send_message(int(tg_id), f"✅ Depozit muvaffaqiyatli!\n💰 {int(dep_amount):,} UZS")
        except:
            pass
        await bot.send_message(ADMIN_ID, f"✅ AVTOMATIK TASDIQLANDI: {user_id_1win}, {int(dep_amount):,} UZS")
    else:
        update_deposit_status(dep_id, "failed")
        error_msg = result.get('message', 'Nomaʼlum xatolik')
        await bot.send_message(ADMIN_ID, f"❌ API xatosi: {error_msg}")

# ==================== MAIN ====================
async def main():
    print("🚀 Bot ishga tushmoqda...")
    if SESSION_STRING:
        await userbot_client.start()
    else:
        await userbot_client.start(phone=phone)
        session_str = userbot_client.session.save()
        print(f"\n📝 USERBOT_SESSION:\n{session_str}\n")
    print("✅ Userbot OK")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
