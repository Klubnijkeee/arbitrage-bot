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

# Список криптовалют для оплаты (поддерживаемые CryptoBot)
SUPPORTED_CRYPTOS = [
    "BTC", "ETH", "BNB", "USDT", "USDC", 
    "TRX", "TON", "MATIC", "SOL", "LTC"
]

# ========== CRYPTOBOT API ==========
class CryptoBotAPI:
    def __init__(self, token):
        self.token = token
        self.base_url = "https://pay.crypt.bot/api"
        
    async def create_invoice(self, user_id, amount, currency="USD", description=""):
        """Создание инвойса в CryptoBot"""
        try:
            payload = {
                "amount": str(amount),
                "currency": currency,
                "description": description,
                "paid_btn_name": "callback",
                "paid_btn_url": f"https://t.me/your_bot?start=payment_success_{user_id}",
                "payload": str(user_id)  # Для идентификации пользователя
            }
            
            response = requests.post(
                f"{self.base_url}/createInvoice",
                headers={"Crypto-Pay-API-Token": self.token},
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    invoice = data.get("result")
                    return {
                        'invoice_id': invoice.get('invoice_id'),
                        'hash': invoice.get('hash'),
                        'bot_invoice_url': invoice.get('bot_invoice_url'),
                        'pay_url': invoice.get('pay_url'),
                        'amount': invoice.get('amount'),
                        'currency': invoice.get('currency'),
                        'status': invoice.get('status')
                    }
                else:
                    print(f"Ошибка CryptoBot: {data.get('error')}")
                    return None
            else:
                print(f"HTTP ошибка: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Ошибка CryptoBot API: {e}")
            return None
    
    async def get_invoice(self, invoice_id):
        """Получение информации об инвойсе"""
        try:
            response = requests.post(
                f"{self.base_url}/getInvoices",
                headers={"Crypto-Pay-API-Token": self.token},
                json={"invoice_ids": str(invoice_id)},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok") and data.get("result", {}).get("items"):
                    return data["result"]["items"][0]
            return None
        except Exception as e:
            print(f"Ошибка получения инвойса: {e}")
            return None
    
    async def get_exchange_rates(self):
        """Получение курсов обмена"""
        try:
            response = requests.get(
                f"{self.base_url}/getExchangeRates",
                headers={"Crypto-Pay-API-Token": self.token},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return data.get("result", [])
            return []
        except Exception as e:
            print(f"Ошибка получения курсов: {e}")
            return []
    
    async def get_balance(self):
        """Получение баланса кошелька"""
        try:
            response = requests.get(
                f"{self.base_url}/getBalance",
                headers={"Crypto-Pay-API-Token": self.token},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return data.get("result", [])
            return []
        except Exception as e:
            print(f"Ошибка получения баланса: {e}")
            return []

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
                  currency TEXT DEFAULT 'USD',
                  crypto_amount REAL,
                  crypto_currency TEXT,
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

def update_setting(user_id, setting, value):
    conn = sqlite3.connect('cryptobot.db')
    c = conn.cursor()
    
    if setting in ['networks', 'brokers']:
        value = json.dumps(value)
    
    c.execute(f'''UPDATE users SET {setting} = ? WHERE user_id = ?''', 
              (value, user_id))
    conn.commit()
    conn.close()

def increment_scans(user_id):
    conn = sqlite3.connect('cryptobot.db')
    c = conn.cursor()
    c.execute('''UPDATE users SET total_scans = total_scans + 1 WHERE user_id = ?''', 
              (user_id,))
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

def save_payment(user_id, invoice_id, invoice_hash, amount, days):
    """Сохранение информации о платеже"""
    conn = sqlite3.connect('cryptobot.db')
    c = conn.cursor()
    
    c.execute('''INSERT OR REPLACE INTO payments 
                 (user_id, invoice_id, invoice_hash, amount, days, status) 
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (user_id, invoice_id, invoice_hash, amount, days, 'active'))
    
    conn.commit()
    conn.close()

def update_payment_status(invoice_id, status, crypto_amount=None, crypto_currency=None):
    """Обновление статуса платежа"""
    conn = sqlite3.connect('cryptobot.db')
    c = conn.cursor()
    
    update_fields = "status = ?, paid_at = CURRENT_TIMESTAMP"
    params = [status]
    
    if crypto_amount and crypto_currency:
        update_fields += ", crypto_amount = ?, crypto_currency = ?"
        params.extend([crypto_amount, crypto_currency])
    
    params.append(invoice_id)
    
    c.execute(f'''UPDATE payments SET {update_fields} WHERE invoice_id = ?''', params)
    
    # Если платеж оплачен, активируем подписку
    if status == 'paid':
        c.execute('''SELECT user_id, days FROM payments WHERE invoice_id = ?''', (invoice_id,))
        result = c.fetchone()
        if result:
            user_id, days = result
            add_subscription(user_id, days)
    
    conn.commit()
    conn.close()

def get_user_payments(user_id, limit=10):
    """Получение платежей пользователя"""
    conn = sqlite3.connect('cryptobot.db')
    c = conn.cursor()
    
    c.execute('''SELECT * FROM payments 
                 WHERE user_id = ? 
                 ORDER BY created_at DESC 
                 LIMIT ?''', (user_id, limit))
    
    payments = c.fetchall()
    conn.close()
    
    result = []
    for p in payments:
        result.append({
            'id': p[0],
            'user_id': p[1],
            'invoice_id': p[2],
            'invoice_hash': p[3],
            'amount': p[4],
            'currency': p[5],
            'crypto_amount': p[6],
            'crypto_currency': p[7],
            'days': p[8],
            'status': p[9],
            'created_at': p[10],
            'paid_at': p[11]
        })
    
    return result

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========== СОСТОЯНИЯ ==========
class Form(StatesGroup):
    waiting_profit = State()
    waiting_profit_pct = State()
    waiting_volume_custom = State()
    adding_subscription = State()
    broadcast_message = State()

# ========== ГЛАВНОЕ МЕНЮ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    text = message.text or ""
    
    # Обработка успешной оплаты
    if "payment_success" in text:
        parts = text.split("_")
        if len(parts) >= 3:
            target_user_id = int(parts[2])
            if target_user_id == user_id:
                await message.answer(
                    "🎉 <b>Платеж успешно получен!</b>\n\n"
                    "Ваша подписка активирована автоматически.\n"
                    "Теперь вы можете использовать все функции бота!",
                    parse_mode='HTML'
                )
    
    username = message.from_user.username or message.from_user.first_name
    
    create_user(user_id, username)
    user = get_user(user_id)
    
    buttons = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🔥 Сканировать", callback_data="scan")],
        [InlineKeyboardButton(text="⚙️ Объем", callback_data="volume"), 
         InlineKeyboardButton(text="💵 Профит", callback_data="profit")],
        [InlineKeyboardButton(text="📈 Доход %", callback_data="profit_pct"), 
         InlineKeyboardButton(text="🌐 Сеть", callback_data="network")],
        [InlineKeyboardButton(text="🏦 Брокеры", callback_data="brokers")],
        [InlineKeyboardButton(text="💳 Оплатить", callback_data="pay")],
        [InlineKeyboardButton(text="📋 Мои платежи", callback_data="my_payments")],
        [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")]
    ]
    
    if user_id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton(text="👑 Админ", callback_data="admin")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    sub_status = "✅ Активна" if user['subscription_days'] > 0 else "❌ Просрочена"
    
    await message.answer(
        f"🫥 <b>@{username}</b> 🔊 Настройте бота!\n\n"
        f"📊 <b>Объем:</b> ${user['min_volume']}\n"
        f"💵 <b>Профит:</b> ${user['min_profit']}\n"
        f"📈 <b>Доход:</b> {user['min_profit_pct']}%\n\n"
        f"🔐 <b>Подписка:</b> {sub_status}\n"
        f"📈 <b>Сканирований:</b> {user['total_scans']}",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

# ========== ОПЛАТА ЧЕРЕЗ CRYPTOBOT ==========
@dp.callback_query(F.data == "pay")
async def payment_handler(callback: types.CallbackQuery):
    if not CRYPTOBOT_TOKEN:
        await callback.answer("❌ CryptoBot не настроен. Обратитесь к администратору.", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 7 дней - $15", callback_data="tariff_7")],
        [InlineKeyboardButton(text="💰 30 дней - $50", callback_data="tariff_30")],
        [InlineKeyboardButton(text="💰 90 дней - $120", callback_data="tariff_90")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ])
    
    await callback.message.edit_text(
        "💳 <b>Выберите тариф подписки:</b>\n\n"
        "• 7 дней - $15 (тестовый период)\n"
        "• 30 дней - $50 (самый популярный)\n"
        "• 90 дней - $120 (экономия $30)\n\n"
        "✅ <b>Оплата через CryptoBot (@CryptoBot)</b>\n"
        "• Поддержка 10+ криптовалют\n"
        "• Быстрые платежи\n"
        "• Низкие комиссии\n\n"
        "💡 После оплаты подписка активируется автоматически",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("tariff_"))
async def tariff_handler(callback: types.CallbackQuery):
    days = int(callback.data.split("_")[1])
    tariff = TARIFFS.get(days, TARIFFS[30])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Оплатить ${tariff['price']}", callback_data=f"create_invoice_{days}")],
        [InlineKeyboardButton(text="🔙 К тарифам", callback_data="pay")]
    ])
    
    discount_text = f"\n{tariff['discount']}" if tariff['discount'] else ""
    
    await callback.message.edit_text(
        f"💳 <b>Тариф на {days} дней</b>\n\n"
        f"💰 Цена: <b>${tariff['price']}</b>{discount_text}\n"
        f"📅 Срок: <b>{days} дней</b>\n\n"
        f"<b>Что включено:</b>\n"
        f"• Неограниченное сканирование\n"
        f"• Доступ ко всем биржам\n"
        f"• Техническая поддержка\n"
        f"• Обновления бота\n\n"
        f"Нажмите кнопку ниже для оплаты",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("create_invoice_"))
async def create_invoice_handler(callback: types.CallbackQuery):
    days = int(callback.data.split("_")[2])
    tariff = TARIFFS.get(days, TARIFFS[30])
    user_id = callback.from_user.id
    
    await callback.answer("🔄 Создаем счет для оплаты...")
    
    # Создаем инвойс в CryptoBot
    invoice = await cryptobot.create_invoice(
        user_id=user_id,
        amount=tariff['price'],
        currency="USD",
        description=f"Подписка на Arbitrage Bot на {days} дней"
    )
    
    if invoice:
        # Сохраняем платеж в БД
        save_payment(user_id, invoice['invoice_id'], invoice['hash'], tariff['price'], days)
        
        # Создаем клавиатуру с кнопками оплаты
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить в CryptoBot", url=invoice['pay_url'])],
            [InlineKeyboardButton(text="🤖 Оплатить в боте", url=invoice['bot_invoice_url'])],
            [InlineKeyboardButton(text="🔄 Проверить статус", callback_data=f"check_status_{invoice['invoice_id']}")],
            [InlineKeyboardButton(text="📋 Мои платежи", callback_data="my_payments")]
        ])
        
        await callback.message.edit_text(
            f"💳 <b>Счет для оплаты создан!</b>\n\n"
            f"🆔 ID счета: <code>{invoice['invoice_id']}</code>\n"
            f"💰 Сумма: <b>${tariff['price']}</b>\n"
            f"📅 Срок: <b>{days} дней</b>\n\n"
            f"<b>Способы оплаты:</b>\n"
            f"1. <b>В CryptoBot</b> - откройте ссылку в @CryptoBot\n"
            f"2. <b>В браузере</b> - оплатите на сайте\n\n"
            f"<b>Инструкция:</b>\n"
            f"1. Выберите способ оплаты\n"
            f"2. Выберите криптовалюту\n"
            f"3. Оплатите указанную сумму\n"
            f"4. Нажмите 'Проверить статус'\n\n"
            f"✅ Подписка активируется автоматически",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    else:
        await callback.message.edit_text(
            "❌ <b>Не удалось создать счет</b>\n\n"
            "Попробуйте позже или свяжитесь с поддержкой.",
            parse_mode='HTML'
        )

@dp.callback_query(F.data.startswith("check_status_"))
async def check_payment_status(callback: types.CallbackQuery):
    invoice_id = callback.data.replace("check_status_", "")
    
    await callback.answer("🔄 Проверяем статус платежа...")
    
    # Проверяем статус в CryptoBot
    invoice_info = await cryptobot.get_invoice(invoice_id)
    
    if invoice_info:
        status = invoice_info.get('status', 'active')
        status_texts = {
            'active': '⏳ Ожидает оплаты',
            'paid': '✅ Оплачен',
            'expired': '❌ Просрочен'
        }
        
        status_text = status_texts.get(status, status)
        
        if status == 'paid':
            # Обновляем статус в БД
            update_payment_status(
                invoice_id, 
                'paid',
                invoice_info.get('paid_amount'),
                invoice_info.get('paid_asset')
            )
            
            await callback.answer(f"✅ Платеж подтвержден! Подписка активирована.", show_alert=True)
            await cmd_start(callback.message)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Проверить снова", callback_data=f"check_status_{invoice_id}")],
                [InlineKeyboardButton(text="💳 Оплатить другой тариф", callback_data="pay")]
            ])
            
            await callback.message.edit_text(
                f"📊 <b>Статус платежа</b>\n\n"
                f"🆔 ID: <code>{invoice_id}</code>\n"
                f"📊 Статус: <b>{status_text}</b>\n"
                f"💰 Сумма: ${invoice_info.get('amount', 'N/A')}\n\n"
                f"Если вы уже оплатили, подождите подтверждения сети.\n"
                f"Обычно это занимает 1-10 минут.",
                reply_markup=keyboard,
                parse_mode='HTML'
            )
    else:
        await callback.answer("❌ Счет не найден", show_alert=True)

@dp.callback_query(F.data == "my_payments")
async def my_payments_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    payments = get_user_payments(user_id, limit=5)
    
    if not payments:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="pay")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
        ])
        
        await callback.message.edit_text(
            "📋 <b>Мои платежи</b>\n\n"
            "У вас пока нет платежей.\n"
            "Купите подписку, чтобы начать пользоваться ботом!",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    payment_text = "📋 <b>Последние платежи:</b>\n\n"
    
    for i, payment in enumerate(payments, 1):
        status_emoji = "✅" if payment['status'] == 'paid' else "⏳"
        date = payment['created_at'][:10] if payment['created_at'] else "N/A"
        
        payment_text += (
            f"{i}. {status_emoji} <b>${payment['amount']}</b> за {payment['days']} дней\n"
            f"   📅 {date} | 🆔 {payment['invoice_id'][:8]}...\n"
        )
        
        if payment['crypto_amount'] and payment['crypto_currency']:
            payment_text += f"   💰 {payment['crypto_amount']} {payment['crypto_currency']}\n"
        
        payment_text += "\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Новый платеж", callback_data="pay")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="my_payments")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ])
    
    await callback.message.edit_text(payment_text, reply_markup=keyboard, parse_mode='HTML')

# ========== АВТОПРОВЕРКА ПЛАТЕЖЕЙ ==========
async def auto_check_payments():
    """Автоматическая проверка платежей каждую минуту"""
    while True:
        try:
            await asyncio.sleep(60)  # Проверяем каждую минуту
            
            conn = sqlite3.connect('cryptobot.db')
            c = conn.cursor()
            
            # Ищем активные платежи
            c.execute('''SELECT invoice_id, user_id FROM payments 
                        WHERE status = 'active' 
                        AND created_at > datetime('now', '-1 hour')''')
            
            active_payments = c.fetchall()
            conn.close()
            
            for invoice_id, user_id in active_payments:
                try:
                    # Проверяем статус в CryptoBot
                    invoice_info = await cryptobot.get_invoice(invoice_id)
                    
                    if invoice_info and invoice_info.get('status') == 'paid':
                        # Обновляем статус
                        update_payment_status(
                            invoice_id,
                            'paid',
                            invoice_info.get('paid_amount'),
                            invoice_info.get('paid_asset')
                        )
                        
                        # Уведомляем пользователя
                        try:
                            await bot.send_message(
                                user_id,
                                f"🎉 <b>Платеж подтвержден!</b>\n\n"
                                f"Ваша подписка активирована.\n"
                                f"Теперь вы можете использовать все функции бота!\n\n"
                                f"Нажмите /start для начала работы",
                                parse_mode='HTML'
                            )
                        except:
                            pass
                            
                except Exception as e:
                    print(f"Ошибка проверки платежа {invoice_id}: {e}")
                    
        except Exception as e:
            print(f"Ошибка авто-проверки платежей: {e}")
            await asyncio.sleep(300)  # Ждем 5 минут при ошибке

# ========== КОМАНДА ДЛЯ АДМИНА ==========
@dp.message(Command("cryptobot"))
async def cryptobot_info(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    # Получаем баланс
    balance = await cryptobot.get_balance()
    
    # Получаем курсы
    rates = await cryptobot.get_exchange_rates()
    
    text = "💰 <b>Информация о CryptoBot</b>\n\n"
    
    if balance:
        text += "<b>Баланс кошелька:</b>\n"
        for item in balance[:5]:  # Показываем первые 5 валют
            text += f"• {item.get('currency_code')}: {item.get('available', 0)}\n"
        text += "\n"
    
    if rates:
        text += "<b>Курсы обмена (USDT):</b>\n"
        for rate in rates[:5]:  # Показываем первые 5 курсов
            if rate.get('target') == 'USDT':
                text += f"• {rate.get('source')}: {rate.get('rate', 0):.6f}\n"
    
    # Статистика платежей
    conn = sqlite3.connect('cryptobot.db')
    c = conn.cursor()
    c.execute('''SELECT COUNT(*), SUM(amount) FROM payments WHERE status = 'paid' ''')
    stats = c.fetchone()
    conn.close()
    
    if stats and stats[0]:
        text += f"\n<b>Статистика платежей:</b>\n"
        text += f"• Успешных платежей: {stats[0]}\n"
        text += f"• Общая сумма: ${stats[1] or 0:.2f}\n"
    
    await message.answer(text, parse_mode='HTML')

# ========== ОБНОВЛЕННАЯ КОМАНДА START ==========
@dp.message(Command("payments"))
async def payments_command(message: types.Message):
    """Показать историю платежей"""
    user_id = message.from_user.id
    payments = get_user_payments(user_id, limit=10)
    
    if not payments:
        await message.answer(
            "📋 <b>История платежей</b>\n\n"
            "У вас пока нет платежей.\n"
            "Используйте /start → 💳 Оплатить",
            parse_mode='HTML'
        )
        return
    
    text = "📋 <b>История ваших платежей:</b>\n\n"
    
    for payment in payments:
        status = "✅ Оплачен" if payment['status'] == 'paid' else "⏳ Ожидание"
        date = payment['created_at'][:16] if payment['created_at'] else "N/A"
        
        text += (
            f"💰 <b>${payment['amount']}</b> за {payment['days']} дней\n"
            f"📅 {date} | {status}\n"
            f"🆔 {payment['invoice_id'][:12]}...\n"
        )
        
        if payment['crypto_amount'] and payment['crypto_currency']:
            text += f"💎 {payment['crypto_amount']} {payment['crypto_currency']}\n"
        
        text += "─" * 30 + "\n"
    
    await message.answer(text, parse_mode='HTML')

# ========== ДОБАВИМ ОСТАЛЬНЫЕ ОБРАБОТЧИКИ (упрощенные) ==========
@dp.callback_query(F.data == "profile")
async def profile_handler(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    
    sub_info = ""
    if user['subscription_until']:
        try:
            until_date = datetime.fromisoformat(user['subscription_until'])
            sub_info = f"\n📅 До: {until_date.strftime('%d.%m.%Y %H:%M')}"
        except:
            pass
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Продлить подписку", callback_data="pay")],
        [InlineKeyboardButton(text="📋 Мои платежи", callback_data="my_payments")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ])
    
    await callback.message.edit_text(
        f"👤 <b>Профиль @{user['username']}</b>\n\n"
        f"💰 <b>Объем сделки:</b> ${user['min_volume']}\n"
        f"💵 <b>Мин. профит:</b> ${user['min_profit']}\n"
        f"📈 <b>Мин. доход:</b> {user['min_profit_pct']}%\n"
        f"🌐 <b>Сети:</b> {', '.join(user['networks'])}\n"
        f"🏦 <b>Брокеры:</b> {', '.join(user['brokers'])}\n\n"
        f"🔐 <b>Подписка:</b> {user['subscription_days']} дней{sub_info}\n"
        f"📊 <b>Сканирований:</b> {user['total_scans']}",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@dp.callback_query(F.data == "scan")
async def scan_handler(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    
    if user['subscription_days'] <= 0:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="pay")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
        ])
        
        await callback.message.edit_text(
            "❌ <b>Подписка неактивна</b>\n\n"
            "Для использования сканирования необходимо приобрести подписку.\n"
            "Выберите тариф и оплатите через CryptoBot.",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    increment_scans(callback.from_user.id)
    await callback.answer("🔍 Сканирую арбитражные возможности...")
    
    # Имитация сканирования
    await asyncio.sleep(2)
    
    # Тестовые данные
    opportunities = [
        {
            'coin': 'BTC',
            'buy_exchange': 'Binance',
            'buy_price': 51234,
            'sell_exchange': 'Bybit',
            'sell_price': 51456,
            'profit_pct': 0.43,
            'profit_usd': 215
        },
        {
            'coin': 'ETH',
            'buy_exchange': 'KuCoin',
            'buy_price': 2890,
            'sell_exchange': 'Binance',
            'sell_price': 2915,
            'profit_pct': 0.86,
            'profit_usd': 86
        }
    ]
    
    for opp in opportunities:
        message = (
            f"🔥 <b>Арбитражная связка</b>\n\n"
            f"💰 <b>Монета:</b> {opp['coin']}\n"
            f"📊 <b>Объем:</b> ${user['min_volume']}\n\n"
            f"⬇️ <b>Купить на {opp['buy_exchange']}:</b> ${opp['buy_price']}\n"
            f"⬆️ <b>Продать на {opp['sell_exchange']}:</b> ${opp['sell_price']}\n\n"
            f"📈 <b>Прибыль:</b> ${opp['profit_usd']} ({opp['profit_pct']}%)\n"
        )
        await callback.message.reply(message, parse_mode='HTML')
    
    await callback.answer(f"✅ Найдено {len(opportunities)} связок")

# ========== ЗАПУСК БОТА ==========
async def main():
    print("🚀 Запуск бота с CryptoBot...")
    print(f"👑 Админы: {ADMIN_IDS}")
    
    # Запускаем авто-проверку платежей
    asyncio.create_task(auto_check_payments())
    
    # Получаем информацию о CryptoBot
    if CRYPTOBOT_TOKEN:
        balance = await cryptobot.get_balance()
        if balance:
            print(f"💰 CryptoBot баланс: {len(balance)} валют")
        else:
            print("⚠️ Не удалось получить баланс CryptoBot")
    
    print("✅ Бот запущен и готов к работе!")
    print("💳 Система оплаты через CryptoBot активна")
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
