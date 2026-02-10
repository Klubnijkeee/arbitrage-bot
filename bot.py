import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from database import get_user_settings, save_user_settings
from config import ADMIN_ID, DEFAULT_SETTINGS
from scanner import ArbitrageScanner

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scanner = ArbitrageScanner()

class SettingsStates(StatesGroup):
    volume = State()
    profit = State()
    profit_pct = State()
    network = State()
    brokers = State()
    payment = State()

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    settings = get_user_settings(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Сканировать", callback_data="scan_now")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings_menu")],
        [InlineKeyboardButton(text="💳 Оплатить", callback_data="payment")]
    ])
    
    sub_status = f"✅ Подписка: {settings['subscription_days']} дней" if settings['subscription_days'] > 0 else "❌ Требуется оплата"
    
    await message.answer(
        f"🫥 @{username} 🔊 Настройте своего бота сейчас.\n\n"
        f"|Объем|Профит|Доход|\n"
        f"|Сеть|Брокеры|Оплатить|\n"
        f"|Показать все настройки|\n\n"
        f"{sub_status}",
        reply_markup=keyboard, parse_mode='HTML'
    )

@dp.callback_query(F.data == "settings_menu")
async def settings_menu(callback: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Объем", callback_data="set_volume")],
        [InlineKeyboardButton(text="💵 Профит", callback_data="set_profit")],
        [InlineKeyboardButton(text="📈 Доход", callback_data="set_profit_pct")],
        [InlineKeyboardButton(text="🌐 Сеть", callback_data="set_network")],
        [InlineKeyboardButton(text="🏦 Брокеры", callback_data="set_brokers")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    await callback.message.edit_text(
        "🔊 Выберите настройку:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("set_"))
async def settings_handler(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    user_id = callback.from_user.id
    settings = get_user_settings(user_id)
    
    if data == "set_volume":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="50", callback_data="vol_50"), InlineKeyboardButton(text="100", callback_data="vol_100")],
            [InlineKeyboardButton(text="200", callback_data="vol_200"), InlineKeyboardButton(text="300", callback_data="vol_300")],
            [InlineKeyboardButton(text="500", callback_data="vol_500"), InlineKeyboardButton(text="1000", callback_data="vol_1000")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu")]
        ])
        await callback.message.edit_text(
            f"🔊 Выберите минимальный объем сделки (USDT).\nТекущий: {settings['min_volume']} USDT",
            reply_markup=keyboard
        )
    
    elif data == "set_profit":
        await state.set_state(SettingsStates.profit)
        await callback.message.edit_text(
            f"🔊 Установите минимальный профит (USDT).\nТекущий: {settings['min_profit']} USDT\n\n"
            "Отправьте число:"
        )
    
    # ... аналогично для других настроек

@dp.message(Command("help"))
async def help_command(message: types.Message):
    help_text = """🆘 /help

Связка - Это пара криптовалют, которую мы исследуем на возможность сделать выгодную сделку...

💰 Объем - Минимальное количество денег (USDT)...
💵 Профит - Сколько денег заработаем...
📈 Доход - Процент прибыли...

🔄 Trade - Включить торговлю: /trade
💎 Стоимость: $50 за 30 дней. /pay"""
    
    await message.answer(help_text)

@dp.callback_query(F.data == "scan_now")
async def scan_now(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = get_user_settings(user_id)
    
    if settings['subscription_days'] <= 0:
        await callback.answer("❌ Требуется оплата подписки!", show_alert=True)
        return
    
    await callback.answer("🔍 Сканирую...")
    opportunities = scanner.find_arbitrage(
        settings['min_volume'],
        settings['min_profit'],
        settings['min_profit_pct']
    )
    
    if opportunities:
        for opp in opportunities:
            signal = scanner.format_signal(opp, settings['networks'][0])
            await callback.message.reply(signal, parse_mode='HTML')
    else:
        await callback.message.edit_text("❌ Возможностей нет")

async def auto_scanner():
    while True:
        try:
            opportunities = scanner.find_arbitrage(100, 5, 3.0)
            if opportunities:
                signal = scanner.format_signal(opportunities[0])
                await bot.send_message(CHANNEL_ID, signal, parse_mode='HTML')
        except:
            pass
        await asyncio.sleep(30)

async def main():
    scanner.load_markets()
    asyncio.create_task(auto_scanner())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
