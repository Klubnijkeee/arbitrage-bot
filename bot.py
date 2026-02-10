import asyncio
import aioschedule
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from config import BOT_TOKEN, CHANNEL_ID, MIN_PROFIT, CHECK_INTERVAL
from scanner import ArbitrageScanner

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
scanner = ArbitrageScanner()

class ArbitrageStates(StatesGroup):
    waiting_profit = State()

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔥 Сканировать сейчас", callback_data="scan_now"))
    keyboard.add(types.InlineKeyboardButton("⚙️ Настройки", callback_data="settings"))
    
    await message.answer(
        f"🚀 <b>Arbitrage Hunter Bot</b>\n\n"
        f"✅ Автоскан каждые {CHECK_INTERVAL}с\n"
        f"💰 Минимум профит: <b>{MIN_PROFIT}%</b>\n"
        f"📡 Сигналы: {CHANNEL_ID}\n\n"
        "Нажми 'Сканировать сейчас' для теста!",
        reply_markup=keyboard, parse_mode='HTML')

@dp.callback_query_handler(text='scan_now')
async def scan_now(callback: types.CallbackQuery):
    await callback.answer("🔍 Сканирую...")
    opportunities = scanner.find_arbitrage()
    
    if opportunities:
        msg = "🔥 <b>АРБИТРАЖ НАЙДЕН!</b>\n\n"
        for opp in opportunities[:3]:  # топ-3
            msg += (
                f"💱 <b>{opp['symbol']}</b>\n"
                f"Bybit: ${opp['bybit_price']:,.2f} ➡️ "
                f"Binance: ${opp['binance_price']:,.2f}\n"
                f"📈 <b>Профит: {opp['profit_pct']:.2f}%</b>\n"
                f"⏰ {opp['timestamp']}\n\n"
            )
        
        await callback.message.edit_text(msg, parse_mode='HTML')
        await bot.send_message(CHANNEL_ID, msg, parse_mode='HTML')  # в канал
    else:
        await callback.message.edit_text("❌ Арбитража нет. Ждем...")

async def auto_scan():
    """Автоскан каждые 30 сек"""
    print("🔍 Автоскан...")
    opportunities = scanner.find_arbitrage()
    
    if opportunities:
        msg = f"🚨 АРБИТРАЖ! Топ: {opportunities[0]['symbol']} {opportunities[0]['profit_pct']:.2f}%"
        await bot.send_message(CHANNEL_ID, msg, parse_mode='HTML')
        print(f"✅ Сигнал отправлен: {len(opportunities)} возможностей")

if __name__ == '__main__':
    scanner.load_markets()
    aioschedule.every(CHECK_INTERVAL).seconds.do(auto_scan)
    
    # Запуск автоскана
    asyncio.create_task(aioschedule_runner())
    
    executor.start_polling(dp, skip_updates=True)