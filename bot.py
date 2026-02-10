import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
import sqlite3
import json

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("=" * 50)
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не найден!")
    print("=" * 50)
    exit(1)

print(f"✅ BOT_TOKEN получен: {BOT_TOKEN[:10]}...")

# Импортируем настройки
try:
    from config import ADMIN_IDS, CHANNEL_ID, SUBSCRIPTION_PRICE, NOWPAYMENTS_API_KEY
except ImportError:
    ADMIN_IDS = [5899591298]
    CHANNEL_ID = '@testscanset'
    SUBSCRIPTION_PRICE = 50.0
    NOWPAYMENTS_API_KEY = ''

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  username TEXT,
                  min_volume INTEGER DEFAULT 100,
                  min_profit REAL DEFAULT 5,
                  min_profit_pct REAL DEFAULT 3.0,
                  networks TEXT DEFAULT '["BEP20","TRC20"]',
                  brokers TEXT DEFAULT '["KuCoin","Bybit"]',
                  subscription_days INTEGER DEFAULT 30,
                  total_scans INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM users WHERE user_id = ?''', (user_id,))
    user = c.fetchone()
    conn.close()
    
    if user:
        return {
            'user_id': user[0],
            'username': user[1],
            'min_volume': user[2],
            'min_profit': user[3],
            'min_profit_pct': user[4],
            'networks': json.loads(user[5]),
            'brokers': json.loads(user[6]),
            'subscription_days': user[7],
            'total_scans': user[8]
        }
    else:
        return None

def create_user(user_id, username):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)''', 
              (user_id, username))
    conn.commit()
    conn.close()

def update_setting(user_id, setting, value):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    if setting in ['networks', 'brokers']:
        value = json.dumps(value)
    
    c.execute(f'''UPDATE users SET {setting} = ? WHERE user_id = ?''', 
              (value, user_id))
    conn.commit()
    conn.close()

def increment_scans(user_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''UPDATE users SET total_scans = total_scans + 1 WHERE user_id = ?''', 
              (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''SELECT user_id, username, subscription_days, total_scans FROM users ORDER BY created_at DESC''')
    users = c.fetchall()
    conn.close()
    return users

def add_subscription(user_id, days):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''UPDATE users SET subscription_days = subscription_days + ? WHERE user_id = ?''', 
              (days, user_id))
    conn.commit()
    conn.close()

# ========== ИНИЦИАЛИЗАЦИЯ ==========
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========== СОСТОЯНИЯ ==========
class Form(StatesGroup):
    waiting_profit = State()
    waiting_profit_pct = State()
    waiting_volume_custom = State()
    adding_subscription = State()

# ========== ГЛАВНОЕ МЕНЮ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    create_user(user_id, username)
    user = get_user(user_id)
    
    keyboard = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🔥 Сканировать", callback_data="scan")],
        [InlineKeyboardButton(text="⚙️ Объем", callback_data="volume"), 
         InlineKeyboardButton(text="💵 Профит", callback_data="profit")],
        [InlineKeyboardButton(text="📈 Доход %", callback_data="profit_pct"), 
         InlineKeyboardButton(text="🌐 Сеть", callback_data="network")],
        [InlineKeyboardButton(text="🏦 Брокеры", callback_data="brokers")],
        [InlineKeyboardButton(text="💳 Оплатить", callback_data="pay")],
        [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")]
    ]
    
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton(text="👑 Админ", callback_data="admin")])
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    sub_status = "✅ Активна" if user['subscription_days'] > 0 else "❌ Просрочена"
    
    await message.answer(
        f"🫥 <b>@{username}</b> 🔊 Настройте бота!\n\n"
        f"📊 <b>Объем:</b> ${user['min_volume']}\n"
        f"💵 <b>Профит:</b> ${user['min_profit']}\n"
        f"📈 <b>Доход:</b> {user['min_profit_pct']}%\n\n"
        f"🔐 <b>Подписка:</b> {sub_status}\n"
        f"📈 <b>Сканирований:</b> {user['total_scans']}",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# ========== ПРОФИЛЬ ==========
@dp.callback_query(F.data == "profile")
async def profile_handler(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    
    keyboard = [
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        f"👤 <b>Профиль @{user['username']}</b>\n\n"
        f"💰 <b>Объем сделки:</b> ${user['min_volume']}\n"
        f"💵 <b>Мин. профит:</b> ${user['min_profit']}\n"
        f"📈 <b>Мин. доход:</b> {user['min_profit_pct']}%\n"
        f"🌐 <b>Сети:</b> {', '.join(user['networks'])}\n"
        f"🏦 <b>Брокеры:</b> {', '.join(user['brokers'])}\n\n"
        f"🔐 <b>Подписка:</b> {user['subscription_days']} дней\n"
        f"📊 <b>Сканирований:</b> {user['total_scans']}",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# ========== СКАНИРОВАНИЕ ==========
@dp.callback_query(F.data == "scan")
async def scan_handler(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    
    if user['subscription_days'] <= 0:
        await callback.answer("❌ Оплатите подписку!", show_alert=True)
        return
    
    increment_scans(callback.from_user.id)
    await callback.answer("🔍 Сканирую...")
    
    # Имитация сканирования
    await asyncio.sleep(1)
    
    # Тестовые данные
    signals = [
        "👁‍🗨KuCoin -> Bybit (SOL/USDT)\n💰Профит: 8.5 USDT\n🚩Доход: 5.2%",
        "👁‍🗨Gate.io -> HTX (BNB/USDT)\n💰Профит: 12.3 USDT\n🚩Доход: 6.8%"
    ]
    
    for signal in signals[:2]:
        await callback.message.reply(signal)
    
    await callback.answer(f"✅ Найдено: {len(signals)} связок")

# ========== НАСТРОЙКА ОБЪЕМА ==========
@dp.callback_query(F.data == "volume")
async def volume_handler(callback: types.CallbackQuery):
    keyboard = [
        [InlineKeyboardButton(text="50$", callback_data="vol_50"),
         InlineKeyboardButton(text="100$", callback_data="vol_100")],
        [InlineKeyboardButton(text="200$", callback_data="vol_200"),
         InlineKeyboardButton(text="500$", callback_data="vol_500")],
        [InlineKeyboardButton(text="1000$", callback_data="vol_1000"),
         InlineKeyboardButton(text="Свой", callback_data="vol_custom")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        "💰 <b>Выберите объем:</b>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("vol_"))
async def set_volume_handler(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "vol_custom":
        await callback.message.edit_text("💰 Введите свой объем в USD:")
        await state.set_state(Form.waiting_volume_custom)
        return
    
    volume = int(callback.data.split('_')[1])
    update_setting(callback.from_user.id, 'min_volume', volume)
    await callback.answer(f"✅ Объем: ${volume}")
    await cmd_start(callback.message)

@dp.message(Form.waiting_volume_custom)
async def process_custom_volume(message: types.Message, state: FSMContext):
    try:
        volume = int(message.text)
        if volume < 10:
            await message.answer("❌ Минимальный объем: $10")
            return
        
        update_setting(message.from_user.id, 'min_volume', volume)
        await message.answer(f"✅ Объем установлен: ${volume}")
        await state.clear()
        await cmd_start(message)
    except ValueError:
        await message.answer("❌ Введите число!")

# ========== НАСТРОЙКА ПРОФИТА ==========
@dp.callback_query(F.data == "profit")
async def profit_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💵 Введите минимальный профит в USDT (например: 5.5):")
    await state.set_state(Form.waiting_profit)

@dp.message(Form.waiting_profit)
async def process_profit(message: types.Message, state: FSMContext):
    try:
        profit = float(message.text)
        update_setting(message.from_user.id, 'min_profit', profit)
        await message.answer(f"✅ Минимальный профит: ${profit}")
        await state.clear()
        await cmd_start(message)
    except ValueError:
        await message.answer("❌ Введите число!")

# ========== НАСТРОЙКА ПРОЦЕНТА ==========
@dp.callback_query(F.data == "profit_pct")
async def profit_pct_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📈 Введите минимальный процент дохода (например: 3.0):")
    await state.set_state(Form.waiting_profit_pct)

@dp.message(Form.waiting_profit_pct)
async def process_profit_pct(message: types.Message, state: FSMContext):
    try:
        pct = float(message.text)
        update_setting(message.from_user.id, 'min_profit_pct', pct)
        await message.answer(f"✅ Минимальный доход: {pct}%")
        await state.clear()
        await cmd_start(message)
    except ValueError:
        await message.answer("❌ Введите число!")

# ========== ВЫБОР СЕТИ ==========
@dp.callback_query(F.data == "network")
async def network_handler(callback: types.CallbackQuery):
    keyboard = [
        [InlineKeyboardButton(text="BEP20 ✅", callback_data="toggle_BEP20")],
        [InlineKeyboardButton(text="TRC20 ✅", callback_data="toggle_TRC20")],
        [InlineKeyboardButton(text="ERC20", callback_data="toggle_ERC20")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        "🌐 <b>Выберите сети:</b>\n✅ - активные",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_network_handler(callback: types.CallbackQuery):
    network = callback.data.split('_')[1]
    user = get_user(callback.from_user.id)
    
    if network in user['networks']:
        user['networks'].remove(network)
    else:
        user['networks'].append(network)
    
    update_setting(callback.from_user.id, 'networks', user['networks'])
    await network_handler(callback)

# ========== ВЫБОР БРОКЕРОВ ==========
@dp.callback_query(F.data == "brokers")
async def brokers_handler(callback: types.CallbackQuery):
    keyboard = [
        [InlineKeyboardButton(text="KuCoin ✅", callback_data="broker_KuCoin")],
        [InlineKeyboardButton(text="Bybit ✅", callback_data="broker_Bybit")],
        [InlineKeyboardButton(text="OKX", callback_data="broker_OKX")],
        [InlineKeyboardButton(text="Gate.io", callback_data="broker_Gate.io")],
        [InlineKeyboardButton(text="HTX", callback_data="broker_HTX")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        "🏦 <b>Выберите биржи:</b>\n✅ - активные",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("broker_"))
async def toggle_broker_handler(callback: types.CallbackQuery):
    broker = callback.data.split('_')[1]
    user = get_user(callback.from_user.id)
    
    if broker in user['brokers']:
        user['brokers'].remove(broker)
    else:
        user['brokers'].append(broker)
    
    update_setting(callback.from_user.id, 'brokers', user['brokers'])
    await brokers_handler(callback)

# ========== ОПЛАТА ==========
@dp.callback_query(F.data == "pay")
async def payment_handler(callback: types.CallbackQuery):
    payment_url = "https://nowpayments.io/payment"  # Замените на реальную ссылку
    
    keyboard = [
        [InlineKeyboardButton(text="💳 Оплатить $50 (30 дней)", url=payment_url)],
        [InlineKeyboardButton(text="💳 Оплатить $90 (60 дней)", url=f"{payment_url}?amount=90")],
        [InlineKeyboardButton(text="💳 Оплатить $120 (90 дней)", url=f"{payment_url}?amount=120")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        "💳 <b>Выберите тариф:</b>\n\n"
        "• 30 дней - $50\n"
        "• 60 дней - $90 (экономия $10)\n"
        "• 90 дней - $120 (экономия $30)\n\n"
        "После оплаты подписка активируется автоматически в течение 5 минут.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# ========== ПОМОЩЬ ==========
@dp.callback_query(F.data == "help")
async def help_handler(callback: types.CallbackQuery):
    help_text = """🆘 <b>Помощь по боту</b>

<b>Основные функции:</b>
• 🔥 <b>Сканировать</b> - поиск арбитражных возможностей
• ⚙️ <b>Объем</b> - минимальная сумма сделки
• 💵 <b>Профит</b> - минимальная прибыль в USDT
• 📈 <b>Доход %</b> - минимальный процент прибыли
• 🌐 <b>Сеть</b> - выбор блокчейн-сетей
• 🏦 <b>Брокеры</b> - выбор бирж для сканирования
• 💳 <b>Оплатить</b> - покупка подписки

<b>Как работает:</b>
1. Настройте параметры
2. Купите подписку
3. Нажимайте "Сканировать"
4. Получайте сигналы

<b>Поддержка:</b>
@support_username"""
    
    keyboard = [
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(help_text, reply_markup=reply_markup, parse_mode='HTML')

# ========== АДМИН ПАНЕЛЬ ==========
@dp.callback_query(F.data == "admin")
async def admin_panel_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Доступ запрещен", show_alert=True)
        return
    
    users = get_all_users()
    active_users = sum(1 for u in users if u[2] > 0)
    total_scans = sum(u[3] for u in users)
    
    keyboard = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton(text="💰 Выдать подписку", callback_data="admin_give_sub")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        f"👑 <b>Админ панель</b>\n\n"
        f"👥 Пользователей: {len(users)}\n"
        f"✅ Активных: {active_users}\n"
        f"📊 Сканирований: {total_scans}",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    users = get_all_users()
    active_users = sum(1 for u in users if u[2] > 0)
    total_scans = sum(u[3] for u in users)
    
    keyboard = [
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: {len(users)}\n"
        f"✅ Активных подписок: {active_users}\n"
        f"📈 Сканирований всего: {total_scans}\n\n"
        f"<b>Топ пользователей:</b>\n",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    # Добавляем топ-5 пользователей
    top_users = sorted(users, key=lambda x: x[3], reverse=True)[:5]
    text = callback.message.text + "\n"
    for i, (user_id, username, days, scans) in enumerate(top_users, 1):
        text += f"{i}. @{username}: {scans} сканирований, {days} дней подписки\n"
    
    await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode='HTML')

@dp.callback_query(F.data == "admin_users")
async def admin_users_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    users = get_all_users()
    
    keyboard = []
    for user_id, username, days, scans in users[:10]:  # Показываем первые 10
        status = "✅" if days > 0 else "❌"
        btn_text = f"{status} @{username} ({scans})"
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"user_{user_id}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin")])
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        "👥 <b>Список пользователей</b>\n✅ - активная подписка\n❌ - нет подписки\n(число) - сканирований",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("user_"))
async def admin_user_detail_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    user_id = int(callback.data.split('_')[1])
    user = get_user(user_id)
    
    if not user:
        await callback.answer("Пользователь не найден")
        return
    
    keyboard = [
        [InlineKeyboardButton(text="➕ 7 дней", callback_data=f"addsub_{user_id}_7"),
         InlineKeyboardButton(text="➕ 30 дней", callback_data=f"addsub_{user_id}_30")],
        [InlineKeyboardButton(text="➕ 90 дней", callback_data=f"addsub_{user_id}_90")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="admin_users")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        f"👤 <b>Пользователь:</b> @{user['username']}\n"
        f"🆔 ID: {user_id}\n"
        f"📅 Подписка: {user['subscription_days']} дней\n"
        f"📊 Сканирований: {user['total_scans']}\n"
        f"💰 Объем: ${user['min_volume']}\n"
        f"💵 Профит: ${user['min_profit']}\n"
        f"📈 Доход: {user['min_profit_pct']}%",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("addsub_"))
async def admin_add_subscription_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    _, user_id, days = callback.data.split('_')
    user_id = int(user_id)
    days = int(days)
    
    add_subscription(user_id, days)
    
    await callback.answer(f"✅ Добавлено {days} дней пользователю", show_alert=True)
    await admin_user_detail_handler(callback)

@dp.callback_query(F.data == "admin_give_sub")
async def admin_give_sub_handler(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    await callback.message.edit_text(
        "💰 <b>Выдача подписки</b>\n\n"
        "Введите ID пользователя и количество дней через пробел:\n"
        "Пример: <code>123456789 30</code>",
        parse_mode='HTML'
    )
    await state.set_state(Form.adding_subscription)

@dp.message(Form.adding_subscription)
async def process_add_subscription(message: types.Message, state: FSMContext):
    try:
        user_id, days = map(int, message.text.split())
        add_subscription(user_id, days)
        
        # Получаем информацию о пользователе
        user = get_user(user_id)
        username = user['username'] if user else "Неизвестный"
        
        await message.answer(f"✅ Пользователю @{username} добавлено {days} дней подписки")
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"🎉 Вам выдана подписка на {days} дней!\n"
                f"Теперь у вас активная подписка."
            )
        except:
            pass
            
    except ValueError:
        await message.answer("❌ Неверный формат. Пример: 123456789 30")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    
    await state.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_handler(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    await callback.message.edit_text(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Введите сообщение для рассылки всем пользователям:",
        parse_mode='HTML'
    )
    await state.set_state("broadcast_message")

@dp.message(F.text, lambda m: m.from_user.id in ADMIN_IDS)
async def process_broadcast(message: types.Message, state: FSMContext):
    if await state.get_state() == "broadcast_message":
        users = get_all_users()
        sent = 0
        failed = 0
        
        await message.answer(f"📤 Начинаю рассылку для {len(users)} пользователей...")
        
        for user_id, username, _, _ in users:
            try:
                await bot.send_message(user_id, message.text)
                sent += 1
            except:
                failed += 1
            await asyncio.sleep(0.05)  # Задержка чтобы не спамить
        
        await message.answer(
            f"✅ Рассылка завершена:\n"
            f"📤 Отправлено: {sent}\n"
            f"❌ Не отправлено: {failed}"
        )
        
        await state.clear()

# ========== ЗАПУСК БОТА ==========
async def main():
    print("🚀 Запуск бота...")
    print(f"📢 Канал: {CHANNEL_ID}")
    print(f"👑 Админы: {ADMIN_IDS}")
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
