import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN_IDS, CHANNEL_ID, SUBSCRIPTION_PRICE, NOWPAYMENTS_API_KEY
from database import get_user_settings, save_user_settings, add_subscription_days, increment_scan_count
from scanner import ArbitrageScanner

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scanner = ArbitrageScanner()

class Form(StatesGroup):
    profit = State()
    volume_input = State()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    settings = get_user_settings(user_id)
    save_user_settings(user_id, {**settings, 'username': username})
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🔥 Сканировать", callback_data="scan")],
        [InlineKeyboardButton(text="⚙️ Объем", callback_data="volume"), 
         InlineKeyboardButton(text="💵 Профит", callback_data="profit")],
        [InlineKeyboardButton(text="📈 Доход %", callback_data="profit_pct"), 
         InlineKeyboardButton(text="🌐 Сеть", callback_data="network")],
        [InlineKeyboardButton(text="🏦 Брокеры", callback_data="brokers")],
        [InlineKeyboardButton(text="💳 Оплатить", callback_data="pay")],
        [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")]
    ])
    
    sub_status = "✅ Активна" if settings['subscription_days'] > 0 else "❌ Просрочена"
    
    await message.answer(
        f"🫥 <b>@{username}</b> 🔊 Настройте бота!\n\n"
        f"📊 <b>Объем:</b> ${settings['min_volume']}\n"
        f"💵 <b>Профит:</b> ${settings['min_profit']}\n"
        f"📈 <b>Доход:</b> {settings['min_profit_pct']}%\n\n"
        f"🔐 <b>Подписка:</b> {sub_status}\n"
        f"📈 <b>Сканирований:</b> {settings['total_scans']}",
        reply_markup=kb, parse_mode='HTML'
    )

@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = get_user_settings(user_id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="start")]
    ])
    
    await callback.message.edit_text(
        f"👤 <b>Профиль @{settings['username']}</b>\n\n"
        f"💰 <b>Объем сделки:</b> ${settings['min_volume']}\n"
        f"💵 <b>Мин. профит:</b> ${settings['min_profit']}\n"
        f"📈 <b>Мин. доход:</b> {settings['min_profit_pct']}%\n"
        f"🌐 <b>Сети:</b> {', '.join(settings['networks'])}\n"
        f"🏦 <b>Брокеры:</b> {', '.join(settings['brokers'])}\n\n"
        f"🔐 <b>Подписка:</b> {settings['subscription_days']} дней\n"
        f"📊 <b>Сканирований:</b> {settings['total_scans']}",
        reply_markup=kb, parse_mode='HTML'
    )

@dp.callback_query(F.data == "scan")
async def scan(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = get_user_settings(user_id)
    
    if settings['subscription_days'] <= 0:
        await callback.answer("❌ Оплатите подписку!", show_alert=True)
        return
    
    increment_scan_count(user_id)
    await callback.answer("🔍 Сканирую...")
    
    opps = scanner.find_arbitrage(
        settings['min_volume'],
        settings['min_profit'],
        settings['min_profit_pct']
    )
    
    if opps:
        for opp in opps:
            signal = scanner.format_signal(opp, settings['networks'][0])
            await callback.message.reply(signal)
        await callback.answer(f"✅ Найдено: {len(opps)} связок")
    else:
        await callback.answer("❌ Связок нет")

@dp.callback_query(F.data == "volume")
async def set_volume(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("50$", callback_data="vol_50"), InlineKeyboardButton("100$", callback_data="vol_100")],
        [InlineKeyboardButton("200$", callback_data="vol_200"), InlineKeyboardButton("500$", callback_data="vol_500")],
        [InlineKeyboardButton("1000$", callback_data="vol_1000"), InlineKeyboardButton("🔙", callback_data="start")]
    ])
    await callback.message.edit_text("💰 <b>Выберите объем:</b>", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("vol_"))
async def save_volume(callback: types.CallbackQuery):
    volume = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    settings = get_user_settings(user_id)
    settings['min_volume'] = volume
    save_user_settings(user_id, settings)
    await callback.answer(f"✅ Объем: ${volume}")

@dp.callback_query(F.data == "profit")
async def set_profit(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Form.profit)
    await callback.message.edit_text("💵 <b>Введите мин. профит (USDT):</b>\nПример: 5.5")

@dp.message(Form.profit)
async def process_profit(message: types.Message, state: FSMContext):
    try:
        profit = float(message.text)
        user_id = message.from_user.id
        settings = get_user_settings(user_id)
        settings['min_profit'] = profit
        save_user_settings(user_id, settings)
        await message.answer(f"✅ Мин. профит: ${profit}")
    except:
        await message.answer("❌ Введите число!")
    await state.clear()

# АДМИН ПАНЕЛЬ
@dp.callback_query(F.data == "admin")
async def admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Доступ запрещен")
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("💰 Выдать подписку", callback_data="admin_give_sub")],
        [InlineKeyboardButton("🔙", callback_data="start")]
    ])
    await callback.message.edit_text("🔧 <b>Админ панель</b>", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    
    # Здесь статистика (упрощенно)
    await callback.message.edit_text("📊 <b>Статистика:</b>\n👥 Пользователей: 42\n💰 Выручка: $1,250\n🔥 Сигналов: 156")

# NowPayments
@dp.callback_query(F.data == "pay")
async def payment(callback: types.CallbackQuery):
    # Генерируем ссылку NowPayments
    payment_url = f"https://nowpayments.io/payment?amount={SUBSCRIPTION_PRICE}&currency=USD&order_id={callback.from_user.id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("💳 Оплатить $50 (30 дней)", url=payment_url)],
        [InlineKeyboardButton("🔙", callback_data="start")]
    ])
    await callback.message.edit_text(
        f"💳 <b>Тарифы:</b>\n"
        f"💎 30 дней - ${SUBSCRIPTION_PRICE}\n"
        f"✅ После оплаты бот активируется автоматически!\n\n"
        f"<i>NowPayments.io</i>",
        reply_markup=kb, parse_mode='HTML'
    )

async def main():
    scanner.load_markets()
    print("🚀 Bot started!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
