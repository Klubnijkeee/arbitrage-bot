import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== НАСТРОЙКИ ==========
# 1. Получаем BOT_TOKEN из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("=" * 50)
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не найден!")
    print("   Чтобы исправить:")
    print("   1. Зайдите в Render Dashboard")
    print("   2. Выберите ваш сервис 'arbitrage-bot'")
    print("   3. Нажмите 'Environment'")
    print("   4. Добавьте: BOT_TOKEN=ваш_токен_бота")
    print("=" * 50)
    exit(1)

print(f"✅ BOT_TOKEN получен: {BOT_TOKEN[:10]}...")

# 2. Импортируем остальные настройки ПОСЛЕ определения BOT_TOKEN
try:
    from config import ADMIN_IDS, CHANNEL_ID, SUBSCRIPTION_PRICE, NOWPAYMENTS_API_KEY
    from database import get_user_settings, save_user_settings, add_subscription_days, increment_scan_count
    from scanner import ArbitrageScanner
except ImportError as e:
    print(f"⚠️ Ошибка импорта модулей: {e}")
    print("📋 Создаем заглушки для модулей...")
    
    # Заглушки если модули не найдены
    ADMIN_IDS = []
    CHANNEL_ID = '@test_channel'
    SUBSCRIPTION_PRICE = 50.0
    NOWPAYMENTS_API_KEY = ''
    
    # Заглушка для database
    class DatabaseStub:
        @staticmethod
        def get_user_settings(user_id):
            return {
                'username': 'test_user',
                'min_volume': 100,
                'min_profit': 5,
                'min_profit_pct': 3.0,
                'networks': ['BEP20', 'TRC20'],
                'brokers': ['KuCoin', 'Bybit'],
                'subscription_days': 30,
                'total_scans': 0
            }
        
        @staticmethod
        def save_user_settings(user_id, settings):
            print(f"📁 Сохранение настроек для {user_id}: {settings}")
        
        @staticmethod
        def add_subscription_days(user_id, days):
            print(f"📅 Добавлено {days} дней подписки для {user_id}")
        
        @staticmethod
        def increment_scan_count(user_id):
            print(f"🔍 Увеличен счетчик сканирований для {user_id}")
    
    # Создаем стабы
    get_user_settings = DatabaseStub.get_user_settings
    save_user_settings = DatabaseStub.save_user_settings
    add_subscription_days = DatabaseStub.add_subscription_days
    increment_scan_count = DatabaseStub.increment_scan_count

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализируем сканер
try:
    scanner = ArbitrageScanner()
    scanner_loaded = True
except Exception as e:
    print(f"⚠️ Ошибка инициализации сканера: {e}")
    scanner = None
    scanner_loaded = False

# ========== СОСТОЯНИЯ ==========
class Form(StatesGroup):
    profit = State()
    volume_input = State()

# ========== КОМАНДА START ==========
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

@dp.callback_query(F.data == "start")
async def start_callback(callback: types.CallbackQuery):
    """Обработчик кнопки 'Главное меню'"""
    await cmd_start(callback.message)
    await callback.answer()

# ========== ПРОФИЛЬ ==========
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

# ========== СКАНИРОВАНИЕ ==========
@dp.callback_query(F.data == "scan")
async def scan(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = get_user_settings(user_id)
    
    if settings['subscription_days'] <= 0:
        await callback.answer("❌ Оплатите подписку!", show_alert=True)
        return
    
    if not scanner_loaded:
        await callback.answer("❌ Сканер не загружен!", show_alert=True)
        return
    
    increment_scan_count(user_id)
    await callback.answer("🔍 Сканирую...")
    
    try:
        opps = scanner.find_arbitrage(
            settings['min_volume'],
            settings['min_profit'],
            settings['min_profit_pct']
        )
        
        if opps:
            for opp in opps[:3]:  # Показываем только 3 лучшие
                signal = scanner.format_signal(opp, settings['networks'][0])
                await callback.message.reply(signal, parse_mode='HTML')
            await callback.answer(f"✅ Найдено: {len(opps)} связок")
        else:
            await callback.answer("❌ Связок нет")
            
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)[:50]}")

# ========== НАСТРОЙКА ОБЪЕМА ==========
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

# ========== НАСТРОЙКА ПРОФИТА ==========
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

# ========== ДРУГИЕ НАСТРОЙКИ (ЗАГЛУШКИ) ==========
@dp.callback_query(F.data == "profit_pct")
async def profit_pct(callback: types.CallbackQuery):
    await callback.answer("⚙️ Настройка дохода % - в разработке", show_alert=True)

@dp.callback_query(F.data == "network")
async def network(callback: types.CallbackQuery):
    await callback.answer("🌐 Настройка сети - в разработке", show_alert=True)

@dp.callback_query(F.data == "brokers")
async def brokers(callback: types.CallbackQuery):
    await callback.answer("🏦 Настройка брокеров - в разработке", show_alert=True)

@dp.callback_query(F.data == "help")
async def help_cmd(callback: types.CallbackQuery):
    help_text = """🆘 <b>Помощь</b>

<b>Команды:</b>
/start - Главное меню

<b>Настройки:</b>
• Объем - минимальная сумма сделки
• Профит - минимальная прибыль в USDT
• Доход % - минимальный процент прибыли

<b>Сканирование:</b>
Находит арбитражные возможности между биржами.

<b>Оплата:</b>
Подписка дает доступ к сканированию.
Тариф: $50 за 30 дней."""
    
    await callback.message.edit_text(help_text, parse_mode='HTML')

# ========== АДМИН ПАНЕЛЬ ==========
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
    if callback.from_user.id not in ADMIN_IDS: 
        return
    
    await callback.message.edit_text("📊 <b>Статистика:</b>\n👥 Пользователей: 42\n💰 Выручка: $1,250\n🔥 Сигналов: 156", parse_mode='HTML')

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    await callback.answer("👥 Список пользователей - в разработке")

@dp.callback_query(F.data == "admin_give_sub")
async def admin_give_sub(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    await callback.answer("💰 Выдача подписки - в разработке")

# ========== ОПЛАТА NOWPAYMENTS ==========
@dp.callback_query(F.data == "pay")
async def payment(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Генерируем ссылку NowPayments
    if NOWPAYMENTS_API_KEY:
        # Если API ключ есть, создаем платеж
        import requests
        try:
            response = requests.post(
                "https://api.nowpayments.io/v1/invoice",
                headers={"x-api-key": NOWPAYMENTS_API_KEY},
                json={
                    "price_amount": SUBSCRIPTION_PRICE,
                    "price_currency": "usd",
                    "pay_currency": "usdt",
                    "order_id": f"user_{user_id}",
                    "order_description": "Подписка на Arbitrage Bot - 30 дней"
                }
            )
            
            if response.status_code == 201:
                data = response.json()
                payment_url = data.get('invoice_url', '')
            else:
                payment_url = f"https://nowpayments.io/payment?amount={SUBSCRIPTION_PRICE}&currency=USD&order_id={user_id}"
        except:
            payment_url = f"https://nowpayments.io/payment?amount={SUBSCRIPTION_PRICE}&currency=USD&order_id={user_id}"
    else:
        # Простая ссылка
        payment_url = f"https://nowpayments.io/payment?amount={SUBSCRIPTION_PRICE}&currency=USD&order_id={user_id}"
    
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

# ========== АВТОСКАН ==========
async def auto_scanner():
    """Автоматическое сканирование и отправка в канал"""
    while True:
        try:
            if scanner_loaded and CHANNEL_ID:
                opps = scanner.find_arbitrage(100, 5, 3.0)
                if opps:
                    signal = scanner.format_signal(opps[0], 'BEP20')
                    await bot.send_message(CHANNEL_ID, signal, parse_mode='HTML')
                    print(f"📤 Отправлен сигнал в канал: {opps[0]['symbol']}")
        except Exception as e:
            print(f"⚠️ Ошибка автоскана: {e}")
        
        await asyncio.sleep(60)  # Каждые 60 секунд

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    print("🚀 Запуск бота...")
    
    # Загружаем рынки если сканер доступен
    if scanner_loaded:
        try:
            scanner.load_markets()
            print("✅ Рынки загружены")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки рынков: {e}")
    
    # Запускаем автоскан в фоне
    asyncio.create_task(auto_scanner())
    
    # Запускаем бота
    print("🤖 Бот запущен и готов к работе!")
    print(f"📢 Канал: {CHANNEL_ID}")
    print(f"👑 Админы: {ADMIN_IDS}")
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
