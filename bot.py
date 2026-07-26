import asyncio
import logging
import random
import aiohttp
import sqlite3
import re
import os
from datetime import datetime, timedelta
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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Environment variable'lardan o'qish (Railway uchun)
TOKEN = os.getenv("BOT_TOKEN", "8869897716:AAG13rX0nbq3DKvpVx7ZrAHa2zx-Xy9xhd0")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1829563275"))
API_KEY = os.getenv("API_KEY", "51c9fcdaecf3a239cdf85aaeddd098e273b208e505edf2f66d94d3efee562751")
api_id = int(os.getenv("API_ID", "35651244"))
api_hash = os.getenv("API_HASH", "d7283bdd8484f650890dba335104f969")
phone = os.getenv("PHONE", "+998919162323")
SESSION_STRING = os.getenv("USERBOT_SESSION", "")

DEPOSIT_URL = "https://api.1win.win/v1/client/deposit"

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ==================== KARTALAR ====================
CARDS = [
    "9860 3501 4449 2351",
    "9860 2466 0248 6556"
]
card_index = 0

def get_next_card():
    global card_index
    card = CARDS[card_index]
    card_index = (card_index + 1) % len(CARDS)
    return card

def generate_random_amount(amount):
    """Random summa yaratish (0.1% - 0.5% farq bilan)"""
    change = random.uniform(0.1, 0.5)
    if random.choice([True, False]):
        return round(amount * (1 + change / 100), 2)
    else:
        return round(amount * (1 - change / 100), 2)

# ==================== FSM HOLATLAR ====================
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

# ==================== MA'LUMOTLAR BAZASI ====================
DB_PATH = "users.db"
PENDING_DB = "pending.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            joined_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def init_pending_db():
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id_1win TEXT,
            telegram_id TEXT,
            amount REAL,
            random_amount REAL,
            card_number TEXT,
            status TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name, last_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined_date)
        VALUES (?, ?, ?, ?, datetime('now'))
    ''', (user_id, username, first_name, last_name))
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
    cursor.execute('''
        INSERT INTO pending_deposits (user_id_1win, telegram_id, amount, random_amount, card_number, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', datetime('now'))
    ''', (user_id_1win, telegram_id, amount, random_amount, card_number))
    conn.commit()
    conn.close()

def get_pending_deposit_by_amount(incoming_amount):
    """HUMO cardbotdan kelgan summa bo'yicha pending depozitni topish"""
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    
    # 1-usul: random_amount yaxlitlangan holda aniq mos
    cursor.execute('''
        SELECT id, user_id_1win, telegram_id, amount, random_amount, card_number
        FROM pending_deposits
        WHERE status = 'pending' 
        AND CAST(ROUND(random_amount) AS INTEGER) = ?
        ORDER BY created_at DESC LIMIT 1
    ''', (incoming_amount,))
    row = cursor.fetchone()
    
    # 2-usul: ±3 farq bilan
    if not row:
        cursor.execute('''
            SELECT id, user_id_1win, telegram_id, amount, random_amount, card_number
            FROM pending_deposits
            WHERE status = 'pending' 
            AND CAST(ROUND(random_amount) AS INTEGER) BETWEEN ? AND ?
            ORDER BY created_at DESC LIMIT 1
        ''', (incoming_amount - 3, incoming_amount + 3))
        row = cursor.fetchone()
    
    # 3-usul: Asl summa bo'yicha
    if not row:
        cursor.execute('''
            SELECT id, user_id_1win, telegram_id, amount, random_amount, card_number
            FROM pending_deposits
            WHERE status = 'pending' 
            AND CAST(ROUND(amount) AS INTEGER) = ?
            ORDER BY created_at DESC LIMIT 1
        ''', (incoming_amount,))
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

# Ma'lumotlar bazalarini ishga tushirish
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

# ==================== API SO'ROVLARI ====================
async def send_deposit_to_1win(user_id: str, amount: int):
    try:
        headers = {"X-API-KEY": API_KEY, "Content-Type": "application/json"}
        payload = {"userId": int(user_id), "amount": amount}
        async with aiohttp.ClientSession() as session:
            async with session.post(DEPOSIT_URL, json=payload, headers=headers, timeout=30) as resp:
                status = resp.status
                if 200 <= status < 300:
                    try:
                        data = await resp.json()
                    except:
                        data = await resp.text()
                    return {"success": True, "data": data, "status": status}
                else:
                    try:
                        data = await resp.json()
                        error_msg = data.get('message', data.get('error', f'Status {status}'))
                    except:
                        error_msg = await resp.text()
                    return {"success": False, "message": error_msg, "status": status}
    except Exception as e:
        return {"success": False, "message": str(e), "status": 0}

# ==================== BOT HANDLERLAR ====================
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    add_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        message.from_user.last_name or ""
    )
    await message.answer(
        "🏦 **1WIN CASH**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "👋 Xush kelibsiz!\n\n"
        "💎 Hisob to'ldirish\n"
        "💸 Pul yechish\n"
        "🌐 1WIN sayti\n"
        "📞 Admin bilan bog'lanish\n\n"
        "👇 Tanlang:",
        reply_markup=main_menu
    )

@dp.message(lambda message: message.text == "🌐 1WIN SAYTI")
async def website_link(message: types.Message):
    await message.answer(
        "🌐 **1WIN RASMIY SAYTI**\n\n"
        "👉 [Saytga o'tish](https://r1wbmjh.life/v3/aggressive-casino?p=i2ry)\n\n"
        "🔒 Xavfsiz va ishonchli havola!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🌐 SAYTGA O'TISH", url="https://r1wbmjh.life/v3/aggressive-casino?p=i2ry")]
            ]
        )
    )

@dp.message(lambda message: message.text == "📞 ADMIN BILAN BOG'LANISH")
async def admin_contact(message: types.Message):
    await message.answer("👨‍💻 **Admin:** @feruz063\n⏰ 24/7", reply_markup=main_menu)

@dp.message(lambda message: message.text == "/stats" and message.from_user.id == ADMIN_ID)
async def stats_cmd(message: types.Message):
    total = get_total_users()
    pending = get_pending_deposits_count()
    await message.answer(
        f"📊 **BOT STATISTIKASI**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Jami foydalanuvchilar: **{total}** ta\n"
        f"⏳ Kutilayotgan depozitlar: **{pending}** ta"
    )

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
    await message.answer(
        f"👤 **Sizning 1Win ID:** `{user_id}`\n\n✅ Bu sizning ID-ingizmi?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ HA", callback_data="confirm_id_yes")],
                [InlineKeyboardButton(text="❌ YO'Q", callback_data="confirm_id_no")]
            ]
        )
    )
    await state.set_state(DepositState.waiting_confirm)

@dp.callback_query(lambda c: c.data == "confirm_id_yes")
async def confirm_id_yes(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "💰 **Summani kiriting:**\n"
        "⚠️ Minimal: 20,000 so'm\n"
        "Maksimal: 100,000,000 so'm\n\n"
        "Masalan: 100000"
    )
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
            await message.answer("❌ Minimal depozit: 20,000 so'm\n💰 Qayta kiriting:")
            return
        if amount > 100000000:
            await message.answer("❌ Maksimal: 100,000,000 so'm")
            return
        
        data = await state.get_data()
        user_id = data.get('user_id')
        random_amount = generate_random_amount(amount)
        card_number = get_next_card()
        
        # Bazaga qo'shish
        add_pending_deposit(user_id, str(message.from_user.id), amount, random_amount, card_number)
        logging.info(f"Yangi depozit: 1Win ID={user_id}, Amount={amount}, Random={random_amount}, Card={card_number}")
        
        await state.update_data(
            user_amount=amount,
            random_amount=random_amount,
            card_number=card_number,
            user_id_1win=user_id,
            deposit_time=datetime.now().isoformat()
        )
        
        await message.answer(
            f"💳 **TO'LOV UCHUN MA'LUMOTLAR:**\n\n"
            f"📋 Karta raqami: `{card_number}`\n"
            f"💰 So'ralgan summa: {amount:,} UZS\n"
            f"🔢 O'tkaziladigan summa: **{random_amount:,.2f} UZS**\n\n"
            f"⚠️ **AYNAN {random_amount:,.2f} UZS** o'tkazing!\n"
            f"⏰ To'lov 15 daqiqa ichida amalga oshirilishi kerak\n\n"
            f"To'lov qilgach, quyidagi tugmani bosing:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📋 KARTA RAQAMINI NUSXALASH", callback_data=f"copy_{card_number}")],
                    [InlineKeyboardButton(text="✅ TO'LOV QILDIM", callback_data="deposit_done")],
                    [InlineKeyboardButton(text="❌ BEKOR QILISH", callback_data="deposit_cancel")]
                ]
            )
        )
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting!")

@dp.callback_query(lambda c: c.data.startswith('copy_'))
async def copy_card(callback: types.CallbackQuery):
    card = callback.data.split('_', 1)[1]
    await callback.answer("📋 Karta raqami nusxa olindi!", show_alert=True)

@dp.callback_query(lambda c: c.data == "deposit_done")
async def deposit_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    random_amount = data.get('random_amount', 0)
    user_id_1win = data.get('user_id_1win', '')
    
    # Holatni tekshirish
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT status FROM pending_deposits
        WHERE user_id_1win = ? AND random_amount = ? AND status = 'pending'
        ORDER BY created_at DESC LIMIT 1
    ''', (user_id_1win, random_amount))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        # To'lov hali tasdiqlanmagan
        await callback.message.edit_text(
            f"⏳ **TO'LOV TEKSHIRILMOQDA...**\n\n"
            f"💰 O'tkazilgan summa: {random_amount:,.2f} UZS\n\n"
            f"✅ Agar to'lov qilgan bo'lsangiz, 5-10 daqiqa ichida avtomatik tasdiqlanadi.\n"
            f"❌ Agar to'lov qilmagan bo'lsangiz, 15 daqiqadan so'ng so'rov bekor qilinadi.\n\n"
            f"📞 Savollar uchun: @feruz063",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 HOLATNI TEKSHIRISH", callback_data=f"check_status_{user_id_1win}")],
                    [InlineKeyboardButton(text="🏠 BOSH SAHIFA", callback_data="back_main")]
                ]
            )
        )
    else:
        await callback.message.edit_text(
            f"⚠️ **Topilmadi yoki allaqachon tasdiqlangan!**\n\n"
            f"📞 Admin: @feruz063",
            reply_markup=main_menu
        )
    
    await state.clear()
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('check_status_'))
async def check_deposit_status(callback: types.CallbackQuery):
    user_id_1win = callback.data.split('_', 2)[2]
    
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT status, amount FROM pending_deposits
        WHERE user_id_1win = ?
        ORDER BY created_at DESC LIMIT 1
    ''', (user_id_1win,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        status, amount = row
        if status == "success":
            await callback.message.edit_text(
                f"✅ **DEPOZIT TASDIQLANGAN!**\n\n"
                f"💰 {int(amount):,} UZS hisobingizga tushdi.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="🏠 BOSH SAHIFA", callback_data="back_main")]]
                )
            )
        elif status == "failed":
            await callback.message.edit_text(
                f"❌ **XATOLIK YUZ BERDI**\n\n📞 Admin: @feruz063",
                reply_markup=main_menu
            )
        else:
            await callback.answer("⏳ Hali tasdiqlanmagan. Iltimos kuting...", show_alert=True)
    else:
        await callback.answer("❌ Topilmadi", show_alert=True)

@dp.callback_query(lambda c: c.data == "deposit_cancel")
async def deposit_cancel(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id_1win = data.get('user_id_1win', '')
    random_amount = data.get('random_amount', 0)
    
    # Bekor qilish
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE pending_deposits SET status = 'cancelled'
        WHERE user_id_1win = ? AND random_amount = ? AND status = 'pending'
    ''', (user_id_1win, random_amount))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(
        "❌ **Depozit bekor qilindi!**",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🏠 BOSH SAHIFA", callback_data="back_main")]]
        )
    )
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
    await message.answer("💳 **Pulni qaysi kartaga olishni xohlaysiz?**\nKarta raqamini kiriting (faqat raqamlar):")
    await state.set_state(WithdrawState.waiting_card)

@dp.message(WithdrawState.waiting_card)
async def withdraw_card(message: types.Message, state: FSMContext):
    card = message.text.replace(" ", "")
    if len(card) < 15 or not card.isdigit():
        await message.answer("❌ Noto'g'ri karta raqami! Qayta kiriting (faqat raqamlar):")
        return
    await state.update_data(card=card)
    await message.answer(
        "🔑 **1Win dan kelgan kodni kiriting:**\n"
        "(Kod 4 dan 10 belgigacha bo'lishi mumkin)\n"
        "Masalan: 1234, 123456, 1234567890"
    )
    await state.set_state(WithdrawState.waiting_code)

@dp.message(WithdrawState.waiting_code)
async def withdraw_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    
    if len(code) < 4 or len(code) > 10:
        await message.answer("❌ Kod 4 dan 10 belgigacha bo'lishi kerak!\nMasalan: 1234, 123456, 1234567890\n\nQayta kiriting:")
        return
    
    data = await state.get_data()
    user_id = data.get('user_id')
    card = data.get('card')
    
    await message.answer(
        f"✅ **So'rovingiz qabul qilindi!**\n\n"
        f"📝 1Win ID: {user_id}\n"
        f"💳 Karta: {card}\n"
        f"🔑 Kod: `{code}`\n\n"
        f"🔔 Admin tekshirib tasdiqlaydi.\n"
        f"⏰ Odatda 5-15 daqiqa ichida.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 BOSH SAHIFA", callback_data="back_main")]
            ]
        )
    )
    
    await bot.send_message(
        ADMIN_ID,
        f"📤 **YANGI YECHIB OLISH SO'ROVI!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 @{message.from_user.username or 'NoUsername'}\n"
        f"🆔 Telegram ID: {message.from_user.id}\n"
        f"📝 1Win ID: {user_id}\n"
        f"💳 Karta: {card}\n"
        f"🔑 Kod: `{code}`\n"
        f"💰 Summa: **(Admin kiritadi)**",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ TASDIQLASH", callback_data=f"with_admin_accept_{message.from_user.id}_{user_id}_{card}_{code}")],
                [InlineKeyboardButton(text="❌ BEKOR QILISH", callback_data=f"with_admin_reject_{message.from_user.id}")]
            ]
        )
    )
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith('with_admin_accept_'))
async def withdraw_admin_accept(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split('_')
    user_telegram_id = int(parts[3])
    user_id_1win = parts[4]
    card = parts[5] if len(parts) > 5 else ""
    code = parts[6] if len(parts) > 6 else ""
    
    await callback.message.edit_text(
        f"📤 **YECHIB OLISH TASDIQLASH**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Telegram ID: {user_telegram_id}\n"
        f"📝 1Win ID: {user_id_1win}\n"
        f"💳 Karta: {card}\n"
        f"🔑 Kod: `{code}`\n\n"
        f"💰 **Yechiladigan summani kiriting (so'mda):**"
    )
    await state.update_data(
        user_telegram_id=user_telegram_id,
        user_id_1win=user_id_1win,
        card=card,
        code=code
    )
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
        
        await message.answer("⏳ 1Win API ga yuborilmoqda...")
        result = await send_deposit_to_1win(user_id_1win, amount)
        
        if result.get('success', False) or (200 <= result.get('status', 0) < 300):
            await bot.send_message(
                user_telegram_id,
                f"✅ **PUL YECHISH MUVAFFAQIYATLI!**\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 {amount:,} UZS kartangizga yuborildi.\n"
                f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"⏰ Odatda 5-30 daqiqa ichida tushadi.",
                reply_markup=main_menu
            )
            await message.answer(f"✅ **Tasdiqlandi!**\nSumma: {amount:,} UZS\nFoydalanuvchiga xabar yuborildi.")
        else:
            error_msg = result.get('message', 'Nomaʼlum xatolik')
            await bot.send_message(
                user_telegram_id,
                f"❌ **XATOLIK!**\n{error_msg}\n📞 Admin: @feruz063",
                reply_markup=main_menu
            )
            await message.answer(f"❌ API xatoligi: {error_msg}")
        
        await state.clear()
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting!")

@dp.callback_query(lambda c: c.data.startswith('with_admin_reject_'))
async def withdraw_admin_reject(callback: types.CallbackQuery):
    user_telegram_id = int(callback.data.split('_')[3])
    await bot.send_message(user_telegram_id, "❌ **Pul yechish so'rovi bekor qilindi.**\n📞 Admin: @feruz063", reply_markup=main_menu)
    await callback.message.edit_text("❌ Yechib olish bekor qilindi.")

# ==================== ORQAGA ====================
@dp.callback_query(lambda c: c.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🏠 Bosh sahifa", reply_markup=main_menu)

# ==================== USERBOT - HUMO CARDBOTNI KUZATISH ====================
# Session string orqali userbot yaratish
if SESSION_STRING:
    userbot_client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash)
else:
    userbot_client = TelegramClient('userbot_session', api_id, api_hash)

@userbot_client.on(events.NewMessage(chats=['@HUMOcardbot']))
async def humo_handler(event):
    message = event.message.text
    logging.info(f"📩 HUMO xabar keldi")
    
    # Adminga to'liq xabarni yuborish
    await bot.send_message(ADMIN_ID, f"📩 **HUMO XABAR:**\n\n{message}")
    
    # "To'ldirish" so'zini tekshirish
    if "To'ldirish" not in message:
        logging.info("⏭️ 'To'ldirish' emas, o'tkazib yuborildi")
        return
    
    logging.info("✅ 'To'ldirish' xabari topildi!")
    
    # ➕ belgisi yonidagi summani olish
    amount_match = re.search(r'[\+➕]\s*(\d[\d\.]*,\d{2})\s*UZS', message)
    
    if amount_match:
        amount_str = amount_match.group(1).replace(".", "").replace(",", ".")
        incoming_amount = round(float(amount_str))
        logging.info(f"💰 ➕ dan olingan summa: {incoming_amount}")
    else:
        # Barcha summalarni topib, eng kichigini olish
        all_amounts = re.findall(r'(\d[\d\.]*,\d{2})\s*UZS', message)
        if not all_amounts:
            await bot.send_message(ADMIN_ID, "❌ Summa topilmadi!")
            return
        
        amounts = []
        for amt in all_amounts:
            amount_str = amt.replace(".", "").replace(",", ".")
            amounts.append(round(float(amount_str)))
        
        incoming_amount = min(amounts)
        logging.info(f"💰 Eng kichik summa: {incoming_amount} (barcha: {amounts})")
    
    await bot.send_message(ADMIN_ID, f"🔍 Qidirilayotgan summa: **{incoming_amount}** UZS")
    
    # Bazadan qidirish
    deposit = get_pending_deposit_by_amount(incoming_amount)
    
    if not deposit:
        logging.info(f"❌ {incoming_amount} UZS uchun depozit topilmadi")
        await bot.send_message(ADMIN_ID, f"❌ **Topilmadi!**\nSumma: {incoming_amount} UZS\nBazada mos depozit yo'q.")
        return
    
    deposit_id, user_id_1win, telegram_id, amount, random_amount, card_number = deposit
    logging.info(f"✅ Depozit topildi! ID={deposit_id}")
    await bot.send_message(
        ADMIN_ID,
        f"✅ **DEPOZIT TOPILDI!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: {deposit_id}\n"
        f"👤 1Win ID: {user_id_1win}\n"
        f"💬 Telegram ID: {telegram_id}\n"
        f"💰 So'ralgan: {amount:,} UZS\n"
        f"🔢 Random: {random_amount:,.2f} UZS"
    )
    
    # 1Win API ga yuborish
    await bot.send_message(ADMIN_ID, "⏳ 1Win API ga so'rov yuborilmoqda...")
    result = await send_deposit_to_1win(user_id_1win, int(amount))
    logging.info(f"API natija: {result}")
    
    if result.get("success", False) or (200 <= result.get("status", 0) < 300):
        status = "success"
        try:
            await bot.send_message(
                int(telegram_id),
                f"✅ **DEPOZIT TASDIQLANDI!**\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 {int(amount):,} UZS 1Win hisobingizga tushdi.\n"
                f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"🎮 O'yinlar: /start",
                reply_markup=main_menu
            )
            logging.info(f"✅ Foydalanuvchiga xabar yuborildi: {telegram_id}")
        except Exception as e:
            logging.error(f"❌ Foydalanuvchiga xabar yuborishda xatolik: {e}")
        
        await bot.send_message(
            ADMIN_ID,
            f"✅ **AVTOMATIK TASDIQLANDI!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 1Win ID: {user_id_1win}\n"
            f"💰 Summa: {int(amount):,} UZS\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
    else:
        status = "failed"
        error_msg = result.get('message', 'Nomaʼlum xatolik')
        try:
            await bot.send_message(
                int(telegram_id),
                f"❌ **XATOLIK YUZ BERDI**\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"Xatolik: {error_msg}\n\n"
                f"📞 Adminga murojaat qiling: @feruz063",
                reply_markup=main_menu
            )
        except Exception as e:
            logging.error(f"❌ Foydalanuvchiga xabar yuborishda xatolik: {e}")
        
        await bot.send_message(
            ADMIN_ID,
            f"❌ **XATOLIK!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 1Win ID: {user_id_1win}\n"
            f"💰 Summa: {int(amount):,} UZS\n"
            f"⚠️ Xatolik: {error_msg}\n\n"
            f"Qo'lda tekshirish kerak!"
        )
    
    # Holatni yangilash
    update_deposit_status(deposit_id, status)
    logging.info(f"✅ Holat yangilandi: {deposit_id} -> {status}")

# ==================== ASOSIY ISHGA TUSHIRISH ====================
async def main():
    print("=" * 50)
    print("🚀 1WIN CASH BOT ISHGA TUSHMOQDA...")
    print("=" * 50)
    
    # Userbotni ishga tushirish
    try:
        if not SESSION_STRING:
            print("📝 Session string topilmadi, telefon raqam orqali kirish...")
            await userbot_client.start(phone=phone)
            session_string = userbot_client.session.save()
            print(f"\n⚠️ USERBOT_SESSION ni Railway Environment ga qo'shing:\n{session_string}\n")
            await bot.send_message(ADMIN_ID, f"📝 **USERBOT_SESSION:**\n\n`{session_string}`\n\n⚠️ Buni Railway Environment ga qo'shing!")
        else:
            await userbot_client.start()
        
        print("✅ Userbot ishga tushdi!")
        print("📡 @HUMOcardbot kuzatilmoqda...")
        
        # Userbotni background da ishga tushirish
        asyncio.create_task(userbot_client.run_until_disconnected())
        
    except Exception as e:
        print(f"❌ Userbot ishga tushmadi: {e}")
        await bot.send_message(ADMIN_ID, f"❌ Userbot xatosi: {e}")
    
    # Bot polling
    try:
        print("✅ Bot polling boshlandi!")
        await bot.send_message(ADMIN_ID, "✅ **Bot ishga tushdi!**\n📡 @HUMOcardbot kuzatilmoqda...")
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Bot polling xatosi: {e}")
        await bot.send_message(ADMIN_ID, f"❌ Bot xatosi: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot to'xtatildi!")
    except Exception as e:
        print(f"❌ Xatolik: {e}")
