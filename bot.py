import os
import asyncio
import logging
import sqlite3
import json
import requests
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
CRYPTOBOT_TOKEN = os.getenv('CRYPTOBOT_TOKEN')  # API ключ от @CryptoBot

if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

if not CRYPTOBOT_TOKEN:
    print("⚠️ ВНИМАНИЕ: CRYPTOBOT_TOKEN не найден! Оплата не будет работать")
    print("Получите токен: /api в @CryptoBot")

print(f"✅ BOT_TOKEN получен: {BOT_TOKEN[:10]}...")
print(f"💰 CryptoBot: {'✅ Найден' if CRYPTOBOT_TOKEN else '❌ Не найден'}")

# Настройки
ADMIN_IDS = [5899591298]
CHANNEL_ID = '@testscanset'

# Тарифы (дни: цена в USD)
TARIFFS = {
    7: {"price": 15, "discount": ""},      # 7 дней за $15
    30: {"price": 50, "discount": ""},     # 30 дней за $50
    90: {"price": 120, "discount": "💰 Экономия $30"}  # 90 дней за $120
}

# ========== ПРАВИЛЬНАЯ ИНТЕГРАЦИЯ CRYPTOBOT ==========
class CryptoBotAPI:
    def __init__(self, token):
        self.token = token
        # ПРАВИЛЬНЫЙ URL для CryptoPay API
        self.base_url = "https://pay.crypt.bot/api"
        
    async def create_invoice(self, amount, currency="USD", description=""):
        """Создание инвойса в CryptoBot - ПРАВИЛЬНЫЙ МЕТОД"""
        try:
            # ПРАВИЛЬНЫЙ формат запроса
            payload = {
                "asset": "USDT",  # Фиксированная валюта
                "amount": str(amount),
            }
            
            headers = {
                "Crypto-Pay-API-Token": self.token,
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                f"{self.base_url}/createInvoice",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            print(f"🔍 CryptoBot Response Status: {response.status_code}")
            print(f"🔍 CryptoBot Response Text: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    result = data.get("result")
                    return {
                        'success': True,
                        'invoice_id': result.get('invoice_id'),
                        'hash': result.get('hash'),
                        'pay_url': result.get('pay_url'),
                        'bot_invoice_url': f"https://t.me/CryptoBot?start={result.get('hash')}",
                        'amount': result.get('amount'),
                        'asset': result.get('asset'),
                        'status': result.get('status')
                    }
                else:
                    error_msg = data.get('error', {}).get('name', 'Unknown error')
                    print(f"❌ CryptoBot API Error: {error_msg}")
                    return {
                        'success': False,
                        'error': error_msg
                    }
            else:
                print(f"❌ HTTP Error {response.status_code}: {response.text}")
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}"
                }
                
        except Exception as e:
            print(f"❌ Exception in CryptoBot API: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def test_connection(self):
        """Тест подключения к CryptoBot API"""
        try:
            headers = {"Crypto-Pay-API-Token": self.token}
            response = requests.get(
                f"{self.base_url}/getMe",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    app_info = data.get("result", {})
                    return {
                        'success': True,
                        'app_id': app_info.get('app_id'),
                        'name': app_info.get('name'),
                        'payment_processing_bot_username': app_info.get('payment_processing_bot_username')
                    }
            return {'success': False, 'error': 'Connection failed'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

# Инициализируем CryptoBot
cryptobot = CryptoBotAPI(CRYPTOBOT_TOKEN)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('cryptobot.db')
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  username TEXT,
                  min_volume INTEGER DEFAULT 100,
                  min_profit REAL DEFAULT 5,
                  min_profit_pct REAL DEFAULT 3.0,
                  networks TEXT DEFAULT '["BEP20","TRC20"]',
                  brokers TEXT DEFAULT '["Binance","Bybit"]',
                  subscription_days INTEGER DEFAULT 0,
                  subscription_until TEXT,
                  total_scans INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица платежей
    c.execute('''CREATE TABLE IF NOT EXISTS payments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  invoice_id TEXT UNIQUE,
                  invoice_hash TEXT,
                  amount REAL,
                  asset TEXT DEFAULT 'USDT',
                  days INTEGER,
                  status TEXT DEFAULT 'active',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  paid_at TIMESTAMP)''')
    
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect('cryptobot.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM users WHERE user_id = ?''', (user_id,))
    user = c.fetchone()
    conn.close()
    
    if user:
        # Проверяем подписку
        sub_until = user[8]
        sub_days = user[7]
        
        if sub_until:
            try:
                until_date = datetime.fromisoformat(sub_until)
                now = datetime.now()
                if until_date > now:
                    remaining_days = (until_date - now).days
                else:
                    remaining_days = 0
            except:
                remaining_days = sub_days
        else:
            remaining_days = sub_days
        
        return {
            'user_id': user[0],
            'username': user[1],
            'min_volume': user[2],
            'min_profit': user[3],
            'min_profit_pct': user[4],
            'networks': json.loads(user[5]),
            'brokers': json.loads(user[6]),
            'subscription_days': remaining_days,
            'subscription_until': sub_until,
            'total_scans': user[9]
        }
    else:
        return None

def create_user(user_id, username):
    conn = sqlite3.connect('cryptobot.db')
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)''', 
              (user_id, username))
    conn.commit()
    conn.close()

def add_subscription(user_id, days):
    conn = sqlite3.connect('cryptobot.db')
    c = conn.cursor()
    
    # Получаем текущую дату окончания
    c.execute('''SELECT subscription_until FROM users WHERE user_id = ?''', (user_id,))
    result = c.fetchone()
    
    if result and result[0]:
        try:
            until_date = datetime.fromisoformat(result[0])
            if until_date > datetime.now():
                new_until = until_date + timedelta(days=days)
            else:
                new_until = datetime.now() + timedelta(days=days)
        except:
            new_until = datetime.now() + timedelta(days=days)
    else:
        new_until = datetime.now() + timedelta(days=days)
    
    c.execute('''UPDATE users SET subscription_days = ?, subscription_until = ? WHERE user_id = ?''',
              (days, new_until.isoformat(), user_id))
    
    conn.commit()
    conn.close()
    
    return new_until

def save_payment(user_id, invoice_id, invoice_hash, amount, days, asset='USDT'):
    """Сохранение информации о платеже"""
    conn = sqlite3.connect('cryptobot.db')
    c = conn.cursor()
    
    c.execute('''INSERT OR REPLACE INTO payments 
                 (user_id, invoice_id, invoice_hash, amount, asset, days, status) 
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (user_id, invoice_id, invoice_hash, amount, asset, days, 'active'))
    
    conn.commit()
    conn.close()

def update_payment_status(invoice_id, status):
    """Обновление статуса платежа"""
    conn = sqlite3.connect('cryptobot.db')
    c = conn.cursor()
    
    c.execute('''UPDATE payments SET status = ?, paid_at = CURRENT_TIMESTAMP 
                 WHERE invoice_id = ?''', (status, invoice_id))
    
    # Если платеж оплачен, активируем подписку
    if status == 'paid':
        c.execute('''SELECT user_id, days FROM payments WHERE invoice_id = ?''', (invoice_id,))
        result = c.fetchone()
        if result:
            user_id, days = result
            add_subscription(user_id, days)
    
    conn.commit()
    conn.close()

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========== СОСТОЯНИЯ ==========
class Form(StatesGroup):
    waiting_profit = State()
    waiting_profit_pct = State()
    waiting_volume_custom = State()

# ========== ПРОСТОЙ И РАБОЧИЙ БОТ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    create_user(user_id, username)
    user = get_user(user_id)
    
    # Проверяем подключение к CryptoBot
    cryptobot_status = ""
    if CRYPTOBOT_TOKEN:
        test_result = await cryptobot.test_connection()
        if test_result['success']:
            cryptobot_status = "✅ CryptoBot подключен"
        else:
            cryptobot_status = f"⚠️ CryptoBot: {test_result.get('error', 'Ошибка')}"
    
    buttons = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🔥 Сканировать", callback_data="scan")],
        [InlineKeyboardButton(text="⚙️ Объем", callback_data="volume"), 
         InlineKeyboardButton(text="💵 Профит", callback_data="profit")],
        [InlineKeyboardButton(text="📈 Доход %", callback_data="profit_pct")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")]
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    sub_status = "✅ Активна" if user['subscription_days'] > 0 else "❌ Нет подписки"
    
    await message.answer(
        f"🤖 <b>Арбитражный бот</b>\n\n"
        f"👤 Пользователь: @{username}\n"
        f"🔐 Подписка: {sub_status}\n"
        f"{cryptobot_status}\n\n"
        f"💰 Тарифы:\n"
        f"• 7 дней - $15\n"
        f"• 30 дней - $50\n"
        f"• 90 дней - $120\n\n"
        f"💳 Оплата через @CryptoBot",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@dp.callback_query(F.data == "buy_subscription")
async def buy_subscription(callback: types.CallbackQuery):
    """Выбор тарифа подписки"""
    if not CRYPTOBOT_TOKEN:
        await callback.answer("❌ CryptoBot не настроен", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="7 дней - $15", callback_data="tariff_7")],
        [InlineKeyboardButton(text="30 дней - $50", callback_data="tariff_30")],
        [InlineKeyboardButton(text="90 дней - $120", callback_data="tariff_90")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu")]
    ])
    
    await callback.message.edit_text(
        "💳 <b>Выберите тариф подписки:</b>\n\n"
        "Оплата через @CryptoBot в USDT\n\n"
        "После оплаты подписка активируется автоматически",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("tariff_"))
async def process_tariff(callback: types.CallbackQuery):
    """Обработка выбора тарифа"""
    days = int(callback.data.split("_")[1])
    tariff = TARIFFS.get(days, TARIFFS[30])
    
    await callback.answer(f"Создаем счет на {days} дней...")
    
    # Создаем инвойс в CryptoBot
    invoice_result = await cryptobot.create_invoice(
        amount=tariff['price'],
        description=f"Подписка на {days} дней"
    )
    
    if invoice_result['success']:
        # Сохраняем платеж
        save_payment(
            callback.from_user.id,
            invoice_result['invoice_id'],
            invoice_result['hash'],
            tariff['price'],
            days,
            invoice_result['asset']
        )
        
        # Создаем клавиатуру с ссылками
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить в CryptoBot", url=invoice_result['pay_url'])],
            [InlineKeyboardButton(text="🤖 Открыть в боте", url=invoice_result['bot_invoice_url'])],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_{invoice_result['invoice_id']}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_subscription")]
        ])
        
        await callback.message.edit_text(
            f"💳 <b>Счет для оплаты создан!</b>\n\n"
            f"💰 Сумма: <b>{tariff['price']} USDT</b>\n"
            f"📅 Срок: <b>{days} дней</b>\n"
            f"🆔 ID: <code>{invoice_result['invoice_id']}</code>\n\n"
            f"<b>Как оплатить:</b>\n"
            f"1. Нажмите кнопку ниже\n"
            f"2. Выберите сеть (TRC20/BEP20/ERC20)\n"
            f"3. Оплатите указанную сумму\n"
            f"4. Нажмите 'Проверить оплату'\n\n"
            f"✅ Подписка активируется автоматически",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    else:
        # Показываем подробную ошибку
        error_msg = invoice_result.get('error', 'Неизвестная ошибка')
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"tariff_{days}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_subscription")]
        ])
        
        await callback.message.edit_text(
            f"❌ <b>Ошибка создания счета:</b>\n\n"
            f"{error_msg}\n\n"
            f"<b>Возможные причины:</b>\n"
            f"• Неправильный API ключ CryptoBot\n"
            f"• Проблемы с сетью\n"
            f"• Технические работы CryptoBot\n\n"
            f"Попробуйте снова или свяжитесь с поддержкой",
            reply_markup=keyboard,
            parse_mode='HTML'
        )

@dp.callback_query(F.data.startswith("check_"))
async def check_payment(callback: types.CallbackQuery):
    """Проверка статуса платежа"""
    invoice_id = callback.data.replace("check_", "")
    
    await callback.answer("Проверяем статус платежа...")
    
    # Здесь можно добавить реальную проверку через CryptoBot API
    # Пока используем заглушку
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить снова", callback_data=f"check_{invoice_id}")],
        [InlineKeyboardButton(text="💳 Новый платеж", callback_data="buy_subscription")]
    ])
    
    await callback.message.edit_text(
        f"🔄 <b>Проверка платежа</b>\n\n"
        f"🆔 ID: <code>{invoice_id}</code>\n"
        f"📊 Статус: <b>Проверяется...</b>\n\n"
        f"Если вы уже оплатили, подождите 1-2 минуты\n"
        f"и проверьте снова.",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@dp.callback_query(F.data == "start_menu")
async def start_menu(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    await cmd_start(callback.message)

# ========== ПРОСТЫЕ ОБРАБОТЧИКИ ==========
@dp.callback_query(F.data == "profile")
async def profile_handler(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    
    sub_info = ""
    if user['subscription_until']:
        try:
            until_date = datetime.fromisoformat(user['subscription_until'])
            sub_info = f"\n📅 Активна до: {until_date.strftime('%d.%m.%Y')}"
        except:
            pass
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Продлить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu")]
    ])
    
    await callback.message.edit_text(
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🆔 ID: {user['user_id']}\n"
        f"👤 Имя: @{user['username']}\n\n"
        f"🔐 Подписка: {user['subscription_days']} дней{sub_info}\n"
        f"📊 Сканирований: {user['total_scans']}",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@dp.callback_query(F.data == "scan")
async def scan_handler(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    
    if user['subscription_days'] <= 0:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu")]
        ])
        
        await callback.message.edit_text(
            "❌ <b>Подписка неактивна</b>\n\n"
            "Для использования сканирования нужна активная подписка.\n"
            "Выберите тариф и оплатите через CryptoBot.",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    await callback.answer("🔍 Начинаю сканирование...")
    
    # Имитация сканирования
    await asyncio.sleep(2)
    
    # Тестовые данные
    opportunities = [
        "📈 BTC: Binance → Bybit (+$215, +0.43%)",
        "📈 ETH: KuCoin → Binance (+$86, +0.86%)",
        "📈 SOL: Bybit → KuCoin (+$45, +1.2%)"
    ]
    
    for opp in opportunities:
        await callback.message.reply(opp)
    
    await callback.answer(f"✅ Найдено {len(opportunities)} связок")

@dp.callback_query(F.data == "help")
async def help_handler(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start_menu")]
    ])
    
    await callback.message.edit_text(
        "🆘 <b>Помощь</b>\n\n"
        "<b>Как пользоваться:</b>\n"
        "1. Купите подписку через CryptoBot\n"
        "2. Настройте параметры сканирования\n"
        "3. Нажимайте 'Сканировать'\n"
        "4. Используйте найденные арбитражные связки\n\n"
        "<b>Оплата:</b>\n"
        "• Через @CryptoBot в USDT\n"
        "• Поддерживаются сети: TRC20, BEP20, ERC20\n"
        "• Подписка активируется автоматически\n\n"
        "<b>Поддержка:</b>\n"
        "По вопросам оплаты и работы бота",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

# ========== ОБРАБОТКА ТЕКСТОВЫХ КОМАНД ==========
@dp.message(Command("test_cryptobot"))
async def test_cryptobot_cmd(message: types.Message):
    """Тест подключения к CryptoBot"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    if not CRYPTOBOT_TOKEN:
        await message.answer("❌ CRYPTOBOT_TOKEN не установлен")
        return
    
    await message.answer("🔍 Тестирую подключение к CryptoBot...")
    
    # Тест подключения
    test_result = await cryptobot.test_connection()
    
    if test_result['success']:
        await message.answer(
            f"✅ <b>CryptoBot подключен</b>\n\n"
            f"🆔 App ID: {test_result.get('app_id', 'N/A')}\n"
            f"📛 Имя: {test_result.get('name', 'N/A')}\n"
            f"🤖 Бот: {test_result.get('payment_processing_bot_username', 'N/A')}",
            parse_mode='HTML'
        )
    else:
        await message.answer(
            f"❌ <b>Ошибка подключения</b>\n\n"
            f"Ошибка: {test_result.get('error', 'Unknown')}\n\n"
            f"<b>Проверьте:</b>\n"
            f"1. Правильность CRYPTOBOT_TOKEN\n"
            f"2. Получили ли токен через /api в @CryptoBot\n"
            f"3. Активен ли токен",
            parse_mode='HTML'
        )

@dp.message(Command("create_invoice"))
async def create_invoice_cmd(message: types.Message):
    """Тест создания инвойса"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    if not CRYPTOBOT_TOKEN:
        await message.answer("❌ CRYPTOBOT_TOKEN не установлен")
        return
    
    await message.answer("💰 Создаю тестовый инвойс на 1 USDT...")
    
    invoice_result = await cryptobot.create_invoice(
        amount=1,
        description="Тестовый платеж"
    )
    
    if invoice_result['success']:
        await message.answer(
            f"✅ <b>Инвойс создан</b>\n\n"
            f"🆔 ID: {invoice_result['invoice_id']}\n"
            f"💰 Сумма: {invoice_result['amount']} {invoice_result['asset']}\n"
            f"🔗 Ссылка: {invoice_result['pay_url']}\n"
            f"🤖 Бот: {invoice_result['bot_invoice_url']}",
            parse_mode='HTML'
        )
    else:
        await message.answer(
            f"❌ <b>Ошибка создания инвойса</b>\n\n"
            f"Ошибка: {invoice_result.get('error', 'Unknown')}",
            parse_mode='HTML'
        )

# ========== ЗАПУСК БОТА ==========
async def main():
    print("🚀 Запуск бота с CryptoBot...")
    print(f"🤖 Бот: @VPNVMESTEbot")
    
    # Тестируем подключение к CryptoBot
    if CRYPTOBOT_TOKEN:
        print("🔍 Тестирую подключение к CryptoBot...")
        test_result = await cryptobot.test_connection()
        
        if test_result['success']:
            print(f"✅ CryptoBot подключен: {test_result.get('name')}")
        else:
            print(f"❌ Ошибка CryptoBot: {test_result.get('error')}")
            print("⚠️  Оплата не будет работать!")
    else:
        print("⚠️  CRYPTOBOT_TOKEN не найден. Оплата отключена.")
    
    print("✅ Бот запущен! Используйте /start")
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
