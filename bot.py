import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BotCommand
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

TOKEN = "8869897716:AAG13rX0nbq3DKvpVx7ZrAHa2zx-Xy9xhd0"
API_KEY = "51c9fcdaecf3a239cdf85aaeddd098e273b208e505edf2f66d94d3efee562751"
BASE_URL = "https://1win.win"

bot = Bot(token=TOKEN)
dp = Dispatcher()

class DepositStates(StatesGroup):
    waiting_for_id = State()
    waiting_for_amount = State()

class WithdrawalStates(StatesGroup):
    waiting_for_id = State()
    waiting_for_code = State()

menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💰 Depozit qilish"), KeyboardButton(text="💸 Pul yechish (Withdrawal)")],
        [KeyboardButton(text="📊 Balansni tekshirish"), KeyboardButton(text="🎁 Promo-kod olish")],
        [KeyboardButton(text="🌐 Saytga kirish (Silka)"), KeyboardButton(text="📲 Ilovani yuklab olish")],
        [KeyboardButton(text="📞 Admin bilan bog'lanish")]
    ],
    resize_keyboard=True
)

ERROR_MESSAGES = {
    "Вывод находится в процессе обработки": "⏳ Pul yechish so'rovi hozirda qayta ishlanmoqda.",
    "Сумма превышает лимиты": "⚠️ Kiritilgan summa belgilangan limitdan ko'p.",
    "Передан неверный идентификатор кассы": "❌ Kassa ID raqami noto'g'ri kiritildi.",
    "Не корректный код": "❌ Tasdiqlash kodi noto'g'ri.",
    "Сумма вывода превышает доступный баланс в кассе": "💰 Yechilayotgan summa kassadagi mavjud balansdan ko'p.",
    "Не корректный идентификатор кассы": "❌ Kassa identifikatori xato.",
    "Не допускается": "🚫 Amallarni bajarishga ruxsat berilmadi (Taqiqlangan).",
    "Вывод не найден": "🔍 Pul yechish so'rovi (Withdrawal) topilmadi.",
    "Пользователь не найден": "👤 Bunday foydalanuvchi (User) tizimda magenta emas."
}

async def send_api_request(endpoint: str, payload: dict):
    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{BASE_URL}/{endpoint}", json=payload, headers=headers) as response:
                res_json = await response.json()
                if response.status == 200:
                    return {"status": "success", "data": res_json}
                elif response.status in [400, 403, 404]:
                    error_text = res_json.get("description") or res_json.get("message") or "Noma'lum xatolik"
                    uz_error = ERROR_MESSAGES.get(error_text, f"⚠️ Tizim xatosi: {error_text}")
                    return {"status": "error", "message": uz_error}
                else:
                    return {"status": "error", "message": f"🤖 Tizimda nosozlik (HTTP {response.status})"}
        except Exception as e:
            return {"status": "exception", "message": f"🌐 Tarmoq xatosi yuz berdi: {str(e)}"}

async def set_main_menu(bot: Bot):
    main_menu_commands = [
        BotCommand(command="/start", description="Botni qayta ishga tushirish"),
    ]
    await bot.set_my_commands(main_menu_commands)

@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Xush kelibsiz! 1Win Cash Agent botiga xush kelibsiz.\n\n"
        "Quyidagi menyudan o'zingizga kerakli bo'limni tanlang:",
        reply_markup=menu_keyboard
    )

@dp.message(F.text == "💰 Depozit qilish")
async def deposit_process(message: types.Message, state: FSMContext):
    await message.answer("📝 **1Win ID** raqamingizni kiriting:")
    await state.set_state(DepositStates.waiting_for_id)

@dp.message(DepositStates.waiting_for_id)
async def deposit_id_received(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ ID raqami faqat raqamlardan iborat bo'lishi kerak. Qaytadan kiriting:")
    await state.update_data(user_id=int(message.text))
    await message.answer("💰 Endi **Depozit summasini** kiriting:")
    await state.set_state(DepositStates.waiting_for_amount)

@dp.message(DepositStates.waiting_for_amount)
async def deposit_amount_received(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Summa faqat raqamlardan iborat bo'lishi kerak. Qaytadan kiriting:")
    amount = int(message.text)
    user_data = await state.get_data()
    user_id = user_data['user_id']
    await message.answer("⏳ Depozit so'rovi yuborilmoqda, kutilmoqda...")
    payload = {"userId": user_id, "amount": amount}
    result = await send_api_request("deposit", payload)
    if result["status"] == "success":
        res_data = result["data"]
        response_text = (
            "✅ **Depozit muvaffaqiyatli amalga oshirildi!**\n\n"
            f"🔹 Transaksiya ID: `{res_data.get('id')}`\n"
            f"🔹 Kassa ID: `{res_data.get('cashId')}`\n"
            f"🔹 Summa: {res_data.get('amount')} UZS\n"
            f"🔹 Foydalanuvchi ID: `{res_data.get('userId')}`"
        )
    else:
        response_text = result["message"]
    await message.answer(response_text, reply_markup=menu_keyboard)
    await state.clear()

@dp.message(F.text == "💸 Pul yechish (Withdrawal)")
async def withdrawal_process(message: types.Message, state: FSMContext):
    await message.answer("📝 Foydalanuvchining **1Win ID** raqamini kiriting:")
    await state.set_state(WithdrawalStates.waiting_for_id)

@dp.message(WithdrawalStates.waiting_for_id)
async def withdrawal_id_received(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ ID raqami faqat raqamlardan iborat bo'lishi kerak. Qaytadan kiriting:")
    await state.update_data(user_id=int(message.text))
    await message.answer("🔑 O'yinchidan olingan **Tasdiqlash kodini** (Code) kiriting:")
    await state.set_state(WithdrawalStates.waiting_for_code)

@dp.message(WithdrawalStates.waiting_for_code)
async def withdrawal_code_received(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Tasdiqlash kodi faqat raqamlardan iborat bo'lishi kerak. Qaytadan kiriting:")
    code = int(message.text)
    user_data = await state.get_data()
    user_id = user_data['user_id']
    await message.answer("🔄 Yechib olish so'rovi tasdiqlanmoqda...")
    payload = {"userId": user_id, "code": code}
    result = await send_api_request("withdrawal", payload)
    if result["status"] == "success":
        res_data = result["data"]
        response_text = (
            "✅ **Mablag' yechish muvaffaqiyatli tasdiqlandi!**\n\n"
            f"🔹 Transaksiya ID: `{res_data.get('id')}`\n"
            f"🔹 Kassa ID: `{res_data.get('cashId')}`\n"
            f"🔹 Yechilgan Summa: {res_data.get('amount')} UZS\n"
            f"🔹 Foydalanuvchi ID: `{res_data.get('userId')}`"
        )
    else:
        response_text = result["message"]
    await message.answer(response_text, reply_markup=menu_keyboard)
    await state.clear()

@dp.message(F.text == "📊 Balansni tekshirish")
async def balance_process(message: types.Message):
    await message.answer("💳 Sizning agentlik balansingiz hozirda: 0 UZS")

@dp.message(F.text == "🎁 Promo-kod olish")
async def promo_process(message: types.Message):
    await message.answer("🎁 **Siz uchun maxsus 1Win Promo-kod:**\n\n👉 **Feruz063** 👈\n\nUshbu promo-kodni ro'yxatdan o'tishda kiriting va birinchi depozitingiz uchun **+500% bonus** oling!")

@dp.message(F.text == "🌐 Saytga kirish (Silka)")
async def link_process(message: types.Message):
    await message.answer("🌐 **1Win Rasmiy saytiga kirish havolasi:**\n\n👉 [1Win Saytiga o'tish](https://1win.com) \n\n*(Ushbu havola orqali blokirovkalarsiz to'g'ridan-to'g'ri saytga kira olasiz)*")

@dp.message(F.text == "📲 Ilovani yuklab olish")
async def app_process(message: types.Message):
    await message.answer("📲 **1Win rasmiy mobil ilovasini yuklab oling:**\n\n🤖 [Android uchun yuklash](https://1win.com)\n🍏 [iOS (iPhone) uchun yuklash](https://1win.com)\n\nIlovani o'rnatib, qulay sharoitda pul tiking va yutuqlarni yechib oling!")

@dp.message(F.text == "📞 Admin bilan bog'lanish")
async def admin_process(message: types.Message):
    await message.answer("👨‍💻 **Qo'llab-quvvatlash xizmati:**\n\nSavollar, muammolar yoki takliflar bo'yicha admin bilan bog'lanishingiz mumkin:\n👉 @feruz063")

async def main():
    await set_main_menu(bot)
    print("Bot muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
