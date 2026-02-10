import os
import asyncio
import logging
import sqlite3
import json
import requests
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    print("Добавьте в переменные окружения Render: BOT_TOKEN=ваш_токен")
    exit(1)

print(f"✅ BOT_TOKEN получен: {BOT_TOKEN[:10]}...")

# Настройки
ADMIN_IDS = [5899591298]
CHANNEL_ID = '@testscanset'
SUBSCRIPTION_PRICE = 50.0

# ========== СКАНЕР АРБИТРАЖА ==========
class ArbitrageScanner:
    def __init__(self):
        self.exchange_urls = {
            'Binance': 'https://api.binance.com/api/v3/ticker/price',
            'Bybit': 'https://api.bybit.com/v5/market/tickers?category=spot',
            'KuCoin': 'https://api.kucoin.com/api/v1/market/allTickers',
            'OKX': 'https://www.okx.com/api/v5/market/tickers?instType=SPOT',
            'Gate.io': 'https://api.gateio.ws/api/v4/spot/tickers',
            'HTX': 'https://api.huobi.pro/market/tickers'
        }
        
        self.coin_mapping = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum', 
            'BNB': 'binancecoin',
            'SOL': 'solana',
            'XRP': 'ripple',
            'ADA': 'cardano',
            'DOGE': 'dogecoin',
            'DOT': 'polkadot',
            'AVAX': 'avalanche-2',
            'MATIC': 'matic-network',
            'LINK': 'chainlink',
            'ATOM': 'cosmos'
        }
        
        self.prices_cache = {}
        self.cache_time = {}
        
    async def get_prices(self, exchange):
        """Получаем цены с биржи"""
        try:
            url = self.exchange_urls.get(exchange)
            if not url:
                return {}
                
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                return {}
                
            if exchange == 'Binance':
                data = response.json()
                prices = {}
                for item in data:
                    if item['symbol'].endswith('USDT'):
                        symbol = item['symbol'].replace('USDT', '')
                        prices[symbol] = float(item['price'])
                return prices
                
            elif exchange == 'Bybit':
                data = response.json()
                prices = {}
                if data['retCode'] == 0:
                    for item in data['result']['list']:
                        if item['symbol'].endswith('USDT'):
                            symbol = item['symbol'].replace('USDT', '')
                            prices[symbol] = float(item['lastPrice'])
                return prices
                
            elif exchange == 'KuCoin':
                data = response.json()
                prices = {}
                if data['code'] == '200000':
                    for item in data['data']['ticker']:
                        if item['symbol'].endswith('-USDT'):
                            symbol = item['symbol'].replace('-USDT', '')
                            prices[symbol] = float(item['last'])
                return prices
                
            elif exchange == 'OKX':
                data = response.json()
                prices = {}
                if data['code'] == '0':
                    for item in data['data']:
                        if item['instId'].endswith('-USDT'):
                            symbol = item['instId'].replace('-USDT', '')
                            prices[symbol] = float(item['last'])
                return prices
                
            elif exchange == 'Gate.io':
                data = response.json()
                prices = {}
                for item in data:
                    if item['currency_pair'].endswith('_USDT'):
                        symbol = item['currency_pair'].replace('_USDT', '')
                        prices[symbol] = float(item['last'])
                return prices
                
            elif exchange == 'HTX':
                data = response.json()
                prices = {}
                if data['status'] == 'ok':
                    for item in data['data']:
                        if item['symbol'].endswith('usdt'):
                            symbol = item['symbol'].replace('usdt', '').upper()
                            prices[symbol] = float(item['close'])
                return prices
                
        except Exception as e:
            print(f"❌ Ошибка получения цен с {exchange}: {e}")
            return {}
            
        return {}
    
    async def get_all_prices(self, brokers):
        """Получаем цены со всех выбранных бирж"""
        all_prices = {}
        
        for broker in brokers:
            # Проверяем кэш (кешируем на 30 секунд)
            current_time = datetime.now().timestamp()
            if broker in self.prices_cache and broker in self.cache_time:
                if current_time - self.cache_time[broker] < 30:
                    all_prices[broker] = self.prices_cache[broker]
                    continue
            
            prices = await self.get_prices(broker)
            if prices:
                self.prices_cache[broker] = prices
                self.cache_time[broker] = current_time
                all_prices[broker] = prices
            await asyncio.sleep(0.5)  # Задержка между запросами
        
        return all_prices
    
    async def find_opportunities(self, brokers, min_volume, min_profit, min_profit_pct):
        """Ищем арбитражные возможности"""
        opportunities = []
        
        # Получаем цены со всех бирж
        all_prices = await self.get_all_prices(brokers)
        if len(all_prices) < 2:
            return opportunities
        
        # Ищем общие монеты на всех биржах
        common_coins = set()
        for broker, prices in all_prices.items():
            if not common_coins:
                common_coins = set(prices.keys())
            else:
                common_coins = common_coins.intersection(set(prices.keys()))
        
        # Анализируем каждую монету
        for coin in common_coins:
            try:
                # Собираем цены для этой монеты на всех биржах
                coin_prices = {}
                for broker, prices in all_prices.items():
                    if coin in prices:
                        coin_prices[broker] = prices[coin]
                
                if len(coin_prices) < 2:
                    continue
                
                # Находим самую низкую и высокую цену
                min_broker = min(coin_prices, key=coin_prices.get)
                max_broker = max(coin_prices, key=coin_prices.get)
                min_price = coin_prices[min_broker]
                max_price = coin_prices[max_broker]
                
                if min_price <= 0 or max_price <= 0:
                    continue
                
                # Рассчитываем профит
                profit_pct = ((max_price - min_price) / min_price) * 100
                
                # Рассчитываем количество монет при заданном объеме
                coins_amount = min_volume / min_price
                
                # Комиссии (примерно 0.2% на бирже и 0.1% на вывод)
                fees = 0.003  # 0.3% суммарно
                profit_usd = (coins_amount * max_price * (1 - fees)) - min_volume
                
                # Проверяем условия
                if profit_pct >= min_profit_pct and profit_usd >= min_profit:
                    opportunities.append({
                        'coin': coin,
                        'buy_exchange': min_broker,
                        'buy_price': min_price,
                        'sell_exchange': max_broker,
                        'sell_price': max_price,
                        'profit_pct': round(profit_pct, 2),
                        'profit_usd': round(profit_usd, 2),
                        'volume': min_volume,
                        'coins_amount': round(coins_amount, 4)
                    })
                    
            except Exception as e:
                print(f"Ошибка анализа монеты {coin}: {e}")
                continue
        
        # Сортируем по проценту профита
        opportunities.sort(key=lambda x: x['profit_pct'], reverse=True)
        return opportunities[:10]  # Возвращаем топ-10
    
    def format_signal(self, opportunity, network='BEP20'):
        """Форматируем сигнал для отправки"""
        coin_name = self.coin_mapping.get(opportunity['coin'], opportunity['coin'])
        
        message = f"🔥 <b>АРБИТРАЖНАЯ СВЯЗКА</b>\n\n"
        message += f"💰 <b>Монета:</b> {opportunity['coin']} ({coin_name})\n"
        message += f"📊 <b>Объем:</b> ${opportunity['volume']}\n\n"
        
        message += f"⬇️ <b>ПОКУПКА на {opportunity['buy_exchange']}</b>\n"
        message += f"• Цена: ${opportunity['buy_price']:.8f}\n"
        message += f"• Количество: {opportunity['coins_amount']} {opportunity['coin']}\n"
        message += f"• Сумма: ${opportunity['volume']}\n\n"
        
        message += f"⬆️ <b>ПРОДАЖА на {opportunity['sell_exchange']}</b>\n"
        message += f"• Цена: ${opportunity['sell_price']:.8f}\n"
        message += f"• Выручка: ${opportunity['coins_amount'] * opportunity['sell_price']:.2f}\n\n"
        
        message += f"📈 <b>РЕЗУЛЬТАТ:</b>\n"
        message += f"• Прибыль: ${opportunity['profit_usd']:.2f}\n"
        message += f"• Доходность: {opportunity['profit_pct']:.2f}%\n\n"
        
        message += f"🔗 <b>Ссылки:</b>\n"
        message += f"• Купить: {self.get_exchange_link(opportunity['buy_exchange'], opportunity['coin'])}\n"
        message += f"• Продать: {self.get_exchange_link(opportunity['sell_exchange'], opportunity['coin'])}\n\n"
        
        message += f"⚠️ <b>ВАЖНО:</b>\n"
        message += f"• Проверьте ликвидность\n"
        message += f"• Учитывайте комиссии (0.2% на сделку + 0.1% на вывод)\n"
        message += f"• Сеть вывода: {network}"
        
        return message
    
    def get_exchange_link(self, exchange, coin):
        """Генерируем ссылки на биржи"""
        links = {
            'Binance': f'https://www.binance.com/ru/trade/{coin}_USDT',
            'Bybit': f'https://www.bybit.com/trade/spot/{coin}/USDT',
            'KuCoin': f'https://www.kucoin.com/trade/{coin}-USDT',
            'OKX': f'https://www.okx.com/trade-spot/{coin}-usdt',
            'Gate.io': f'https://www.gate.io/trade/{coin}_USDT',
            'HTX': f'https://www.htx.com/trade/{coin.lower()}_usdt'
        }
        return links.get(exchange, f"{exchange}: {coin}/USDT")

# Инициализируем сканер
scanner = ArbitrageScanner()

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
                  brokers TEXT DEFAULT '["Binance","Bybit"]',
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
    broadcast_message = State()

# ========== ГЛАВНОЕ МЕНЮ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    create_user(user_id, username)
    user = get_user(user_id)
    if not user:
        await message.answer("❌ Ошибка при создании пользователя")
        return
    
    buttons = [
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

@dp.callback_query(F.data == "start")
async def start_callback(callback: types.CallbackQuery):
    await cmd_start(callback.message)
    await callback.answer()

# ========== ПРОФИЛЬ ==========
@dp.callback_query(F.data == "profile")
async def profile_handler(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Пользователь не найден")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="start")]
    ])
    
    await callback.message.edit_text(
        f"👤 <b>Профиль @{user['username']}</b>\n\n"
        f"💰 <b>Объем сделки:</b> ${user['min_volume']}\n"
        f"💵 <b>Мин. профит:</b> ${user['min_profit']}\n"
        f"📈 <b>Мин. доход:</b> {user['min_profit_pct']}%\n"
        f"🌐 <b>Сети:</b> {', '.join(user['networks'])}\n"
        f"🏦 <b>Брокеры:</b> {', '.join(user['brokers'])}\n\n"
        f"🔐 <b>Подписка:</b> {user['subscription_days']} дней\n"
        f"📊 <b>Сканирований:</b> {user['total_scans']}",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

# ========== СКАНИРОВАНИЕ ==========
@dp.callback_query(F.data == "scan")
async def scan_handler(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Пользователь не найден")
        return
    
    if user['subscription_days'] <= 0:
        await callback.answer("❌ Оплатите подписку!", show_alert=True)
        return
    
    increment_scans(callback.from_user.id)
    
    # Показываем статус сканирования
    status_msg = await callback.message.answer("🔍 <b>Начинаю сканирование...</b>", parse_mode='HTML')
    
    try:
        # Получаем настройки пользователя
        brokers = user['brokers']
        min_volume = user['min_volume']
        min_profit = user['min_profit']
        min_profit_pct = user['min_profit_pct']
        
        # Обновляем статус
        await status_msg.edit_text("📡 <b>Получаю цены с бирж...</b>", parse_mode='HTML')
        
        # Ищем возможности
        opportunities = await scanner.find_opportunities(
            brokers, min_volume, min_profit, min_profit_pct
        )
        
        if opportunities:
            await status_msg.edit_text(f"✅ <b>Найдено {len(opportunities)} связок!</b>", parse_mode='HTML')
            
            # Отправляем топ-3 связки
            for i, opp in enumerate(opportunities[:3]):
                try:
                    signal = scanner.format_signal(opp, user['networks'][0] if user['networks'] else 'BEP20')
                    await callback.message.reply(signal, parse_mode='HTML')
                    await asyncio.sleep(0.5)  # Задержка между сообщениями
                except Exception as e:
                    print(f"Ошибка отправки сигнала: {e}")
                    continue
            
            # Предлагаем показать еще
            if len(opportunities) > 3:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Показать все связки", callback_data=f"show_all_{len(opportunities)}")],
                    [InlineKeyboardButton(text="🔙 Главное меню", callback_data="start")]
                ])
                await callback.message.answer(
                    f"📊 Найдено {len(opportunities)} связок. Показано 3 лучших.\n"
                    f"Нажмите 'Показать все' чтобы увидеть остальные.",
                    reply_markup=keyboard
                )
            else:
                await callback.answer(f"✅ Найдено {len(opportunities)} связок")
        else:
            await status_msg.edit_text("❌ <b>Подходящих связок не найдено</b>\n\n"
                                     "Попробуйте:\n"
                                     "• Уменьшить минимальную прибыль\n"
                                     "• Уменьшить минимальный процент\n"
                                     "• Добавить больше бирж", parse_mode='HTML')
            await callback.answer("❌ Связок не найдено")
            
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Ошибка сканирования:</b>\n{str(e)[:200]}", parse_mode='HTML')
        print(f"Ошибка сканирования: {e}")

@dp.callback_query(F.data.startswith("show_all_"))
async def show_all_handler(callback: types.CallbackQuery):
    try:
        count = int(callback.data.split('_')[2])
        await callback.answer(f"Показать все {count} связок")
        
        # Здесь можно добавить логику пагинации
        await callback.message.answer(
            f"📋 Всего найдено {count} связок.\n\n"
            f"Для просмотра всех связок используйте /start и снова запустите сканирование.\n"
            f"Или настройте фильтры для отображения лучших результатов."
        )
    except:
        await callback.answer("❌ Ошибка")

# ========== НАСТРОЙКА ОБЪЕМА ==========
@dp.callback_query(F.data == "volume")
async def volume_handler(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="50$", callback_data="vol_50"),
         InlineKeyboardButton(text="100$", callback_data="vol_100")],
        [InlineKeyboardButton(text="200$", callback_data="vol_200"),
         InlineKeyboardButton(text="500$", callback_data="vol_500")],
        [InlineKeyboardButton(text="1000$", callback_data="vol_1000"),
         InlineKeyboardButton(text="Свой", callback_data="vol_custom")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ])
    
    await callback.message.edit_text(
        "💰 <b>Выберите объем:</b>\nМинимальная сумма для сделки",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("vol_"))
async def set_volume_handler(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "vol_custom":
        await callback.message.edit_text("💰 Введите свой объем в USD:")
        await state.set_state(Form.waiting_volume_custom)
        await callback.answer()
        return
    
    try:
        volume = int(callback.data.split('_')[1])
        update_setting(callback.from_user.id, 'min_volume', volume)
        await callback.answer(f"✅ Объем: ${volume}")
        await cmd_start(callback.message)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}")

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
    await callback.answer()

@dp.message(Form.waiting_profit)
async def process_profit(message: types.Message, state: FSMContext):
    try:
        profit = float(message.text)
        if profit < 0.1:
            await message.answer("❌ Минимальный профит: $0.1")
            return
        
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
    await callback.answer()

@dp.message(Form.waiting_profit_pct)
async def process_profit_pct(message: types.Message, state: FSMContext):
    try:
        pct = float(message.text)
        if pct < 0.1:
            await message.answer("❌ Минимальный доход: 0.1%")
            return
        
        update_setting(message.from_user.id, 'min_profit_pct', pct)
        await message.answer(f"✅ Минимальный доход: {pct}%")
        await state.clear()
        await cmd_start(message)
    except ValueError:
        await message.answer("❌ Введите число!")

# ========== ВЫБОР СЕТИ ==========
@dp.callback_query(F.data == "network")
async def network_handler(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Пользователь не найден")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"BEP20 (BSC) {'✅' if 'BEP20' in user['networks'] else '❌'}", 
            callback_data="toggle_BEP20"
        )],
        [InlineKeyboardButton(
            text=f"TRC20 (TRON) {'✅' if 'TRC20' in user['networks'] else '❌'}", 
            callback_data="toggle_TRC20"
        )],
        [InlineKeyboardButton(
            text=f"ERC20 (Ethereum) {'✅' if 'ERC20' in user['networks'] else '❌'}", 
            callback_data="toggle_ERC20"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ])
    
    await callback.message.edit_text(
        "🌐 <b>Выберите сети для вывода:</b>\n✅ - активные\n❌ - неактивные",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_network_handler(callback: types.CallbackQuery):
    network = callback.data.split('_')[1]
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Пользователь не найден")
        return
    
    if network in user['networks']:
        user['networks'].remove(network)
    else:
        user['networks'].append(network)
    
    update_setting(callback.from_user.id, 'networks', user['networks'])
    await network_handler(callback)
    await callback.answer()

# ========== ВЫБОР БРОКЕРОВ ==========
@dp.callback_query(F.data == "brokers")
async def brokers_handler(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Пользователь не найден")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"Binance {'✅' if 'Binance' in user['brokers'] else '❌'}", 
            callback_data="broker_Binance"
        )],
        [InlineKeyboardButton(
            text=f"Bybit {'✅' if 'Bybit' in user['brokers'] else '❌'}", 
            callback_data="broker_Bybit"
        )],
        [InlineKeyboardButton(
            text=f"KuCoin {'✅' if 'KuCoin' in user['brokers'] else '❌'}", 
            callback_data="broker_KuCoin"
        )],
        [InlineKeyboardButton(
            text=f"OKX {'✅' if 'OKX' in user['brokers'] else '❌'}", 
            callback_data="broker_OKX"
        )],
        [InlineKeyboardButton(
            text=f"Gate.io {'✅' if 'Gate.io' in user['brokers'] else '❌'}", 
            callback_data="broker_Gate.io"
        )],
        [InlineKeyboardButton(
            text=f"HTX {'✅' if 'HTX' in user['brokers'] else '❌'}", 
            callback_data="broker_HTX"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ])
    
    await callback.message.edit_text(
        "🏦 <b>Выберите биржи для сканирования:</b>\n✅ - активные\n❌ - неактивные\n\n"
        "Для арбитража нужно минимум 2 биржи",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("broker_"))
async def toggle_broker_handler(callback: types.CallbackQuery):
    broker = callback.data.split('_')[1]
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Пользователь не найден")
        return
    
    if broker in user['brokers']:
        user['brokers'].remove(broker)
    else:
        user['brokers'].append(broker)
    
    update_setting(callback.from_user.id, 'brokers', user['brokers'])
    await brokers_handler(callback)
    await callback.answer()

# ========== ОПЛАТА ==========
@dp.callback_query(F.data == "pay")
async def payment_handler(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 30 дней - $50", callback_data="pay_30")],
        [InlineKeyboardButton(text="💳 60 дней - $90", callback_data="pay_60")],
        [InlineKeyboardButton(text="💳 90 дней - $120", callback_data="pay_90")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ])
    
    await callback.message.edit_text(
        "💳 <b>Выберите тариф:</b>\n\n"
        "• 30 дней - $50\n"
        "• 60 дней - $90 (экономия $10)\n"
        "• 90 дней - $120 (экономия $30)\n\n"
        "✅ <b>Включает:</b>\n"
        "• Неограниченное сканирование\n"
        "• Доступ ко всем биржам\n"
        "• Техническую поддержку\n"
        "• Обновления бота",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("pay_"))
async def process_payment_handler(callback: types.CallbackQuery):
    try:
        days = int(callback.data.split('_')[1])
        prices = {30: 50, 60: 90, 90: 120}
        
        await callback.answer(f"✅ Тариф на {days} дней выбран. Цена: ${prices[days]}")
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="pay")]
        ])
        
        await callback.message.edit_text(
            f"💳 <b>Оплата тарифа на {days} дней</b>\n\n"
            f"Цена: ${prices[days]}\n\n"
            f"Для оплаты:\n"
            f"1. Переведите ${prices[days]} USDT на адрес:\n"
            f"<code>0x1234567890abcdef1234567890abcdef12345678</code>\n\n"
            f"2. Отправьте хеш транзакции в ответ на это сообщение\n\n"
            f"После подтверждения транзакции подписка будет активирована.",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}")

# ========== ПОМОЩЬ ==========
@dp.callback_query(F.data == "help")
async def help_handler(callback: types.CallbackQuery):
    help_text = """🆘 <b>Помощь по боту</b>

<b>Как работает арбитраж:</b>
1. Бот сканирует цены на разных биржах
2. Находит разницу в ценах одной монеты
3. Рассчитывает прибыль с учетом комиссий
4. Показывает где купить дешевле и продать дороже

<b>Рекомендуемые настройки:</b>
• Объем: $100-1000
• Мин. профит: $5-10
• Мин. доходность: 3-5%
• Биржи: минимум 2-3
• Сети: BEP20 (дешевые комиссии)

<b>Как использовать:</b>
1. Настройте параметры
2. Купите подписку
3. Нажимайте "Сканировать"
4. Используйте найденные связки

<b>Важные моменты:</b>
• Учитывайте комиссии бирж
• Проверяйте ликвидность
• Выводите на проверенные сети

<b>Поддержка:</b>
Для связи: @support"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
    ])
    
    await callback.message.edit_text(help_text, reply_markup=keyboard, parse_mode='HTML')
    await callback.answer()

# ========== АДМИН ПАНЕЛЬ ==========
@dp.callback_query(F.data == "admin")
async def admin_panel_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Доступ запрещен", show_alert=True)
        return
    
    users = get_all_users()
    active_users = sum(1 for u in users if u[2] > 0)
    total_scans = sum(u[3] for u in users)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_users")],
        [InlineKeyboardButton(text="💰 Выдать подписку", callback_data="admin_give_sub")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="start")]
    ])
    
    await callback.message.edit_text(
        f"👑 <b>Админ панель</b>\n\n"
        f"👥 Пользователей: {len(users)}\n"
        f"✅ Активных: {active_users}\n"
        f"📊 Сканирований: {total_scans}",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    users = get_all_users()
    active_users = sum(1 for u in users if u[2] > 0)
    total_scans = sum(u[3] for u in users)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]
    ])
    
    text = f"📊 <b>Статистика бота</b>\n\n"
    text += f"👥 Всего пользователей: {len(users)}\n"
    text += f"✅ Активных подписок: {active_users}\n"
    text += f"📈 Сканирований всего: {total_scans}\n\n"
    text += f"<b>Топ пользователей:</b>\n"
    
    top_users = sorted(users, key=lambda x: x[3], reverse=True)[:5]
    for i, (user_id, username, days, scans) in enumerate(top_users, 1):
        text += f"{i}. @{username or 'Без имени'}: {scans} сканирований, {days} дней подписки\n"
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
    await callback.answer()

@dp.callback_query(F.data == "admin_users")
async def admin_users_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    users = get_all_users()
    
    buttons = []
    for user_id, username, days, scans in users[:10]:
        status = "✅" if days > 0 else "❌"
        btn_text = f"{status} @{username or 'Без имени'} ({scans})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"user_{user_id}")])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        "👥 <b>Список пользователей</b>\n✅ - активная подписка\n❌ - нет подписки\n(число) - сканирований",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("user_"))
async def admin_user_detail_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    try:
        user_id = int(callback.data.split('_')[1])
        user = get_user(user_id)
        
        if not user:
            await callback.answer("Пользователь не найден")
            return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ 7 дней", callback_data=f"addsub_{user_id}_7"),
             InlineKeyboardButton(text="➕ 30 дней", callback_data=f"addsub_{user_id}_30")],
            [InlineKeyboardButton(text="➕ 90 дней", callback_data=f"addsub_{user_id}_90")],
            [InlineKeyboardButton(text="🔙 К списку", callback_data="admin_users")]
        ])
        
        await callback.message.edit_text(
            f"👤 <b>Пользователь:</b> @{user['username']}\n"
            f"🆔 ID: {user_id}\n"
            f"📅 Подписка: {user['subscription_days']} дней\n"
            f"📊 Сканирований: {user['total_scans']}\n"
            f"💰 Объем: ${user['min_volume']}\n"
            f"💵 Профит: ${user['min_profit']}\n"
            f"📈 Доход: {user['min_profit_pct']}%",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}")

@dp.callback_query(F.data.startswith("addsub_"))
async def admin_add_subscription_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    
    try:
        _, user_id, days = callback.data.split('_')
        user_id = int(user_id)
        days = int(days)
        
        add_subscription(user_id, days)
        
        await callback.answer(f"✅ Добавлено {days} дней пользователю", show_alert=True)
        await admin_user_detail_handler(callback)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}")

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
    await callback.answer()

@dp.message(Form.adding_subscription)
async def process_add_subscription(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError("Неверный формат")
        
        user_id = int(parts[0])
        days = int(parts[1])
        
        if days <= 0:
            await message.answer("❌ Количество дней должно быть больше 0")
            return
        
        add_subscription(user_id, days)
        
        user = get_user(user_id)
        username = user['username'] if user else "Неизвестный"
        
        await message.answer(f"✅ Пользователю @{username} добавлено {days} дней подписки")
        
        try:
            await bot.send_message(
                user_id,
                f"🎉 Вам выдана подписка на {days} дней!\n"
                f"Теперь у вас активная подписка."
            )
        except:
            pass
            
    except ValueError as e:
        await message.answer(f"❌ Неверный формат. Пример: 123456789 30")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    
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
    await state.set_state(Form.broadcast_message)
    await callback.answer()

@dp.message(Form.broadcast_message)
async def process_broadcast(message: types.Message, state: FSMContext):
    users = get_all_users()
    sent = 0
    failed = 0
    
    progress_msg = await message.answer(f"📤 Начинаю рассылку для {len(users)} пользователей...")
    
    for user_id, username, _, _ in users:
        try:
            await bot.send_message(user_id, message.text)
            sent += 1
            if sent % 10 == 0:
                await progress_msg.edit_text(f"📤 Отправлено: {sent}/{len(users)}...")
        except:
            failed += 1
        await asyncio.sleep(0.1)
    
    await progress_msg.edit_text(
        f"✅ Рассылка завершена:\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Не отправлено: {failed}"
    )
    
    await state.clear()

# ========== ОБРАБОТКА ПЕРЕВОДОВ ==========
@dp.message(F.text)
async def handle_transaction_hash(message: types.Message):
    # Простая проверка на хеш транзакции
    text = message.text.strip()
    if len(text) > 50 and all(c in 'abcdef0123456789' for c in text.lower()):
        user_id = message.from_user.id
        add_subscription(user_id, 30)  # 30 дней за оплату
        
        await message.answer(
            f"✅ <b>Спасибо за оплату!</b>\n\n"
            f"Ваша подписка активирована на 30 дней.\n"
            f"Теперь вы можете использовать функцию сканирования!\n\n"
            f"Нажмите /start для начала работы",
            parse_mode='HTML'
        )

# ========== АВТО-СКАНИРОВАНИЕ В КАНАЛ ==========
async def auto_scanner_channel():
    """Автоматическое сканирование для канала"""
    while True:
        try:
            await asyncio.sleep(300)  # 5 минут
            
            # Сканируем с базовыми настройками
            brokers = ['Binance', 'Bybit', 'KuCoin']
            opportunities = await scanner.find_opportunities(
                brokers, 1000, 10, 3.0
            )
            
            if opportunities:
                # Берем лучшую связку
                best_opp = opportunities[0]
                if best_opp['profit_pct'] > 5.0:  # Только если доходность >5%
                    signal = scanner.format_signal(best_opp, 'BEP20')
                    
                    try:
                        await bot.send_message(CHANNEL_ID, signal, parse_mode='HTML')
                        print(f"📤 Отправлен сигнал в канал: {best_opp['coin']}")
                    except Exception as e:
                        print(f"Ошибка отправки в канал: {e}")
            
        except Exception as e:
            print(f"❌ Ошибка авто-сканера канала: {e}")
            await asyncio.sleep(60)

# ========== ЗАПУСК БОТА ==========
async def main():
    print("🚀 Запуск бота...")
    print(f"📢 Канал: {CHANNEL_ID}")
    print(f"👑 Админы: {ADMIN_IDS}")
    
    # Запускаем авто-сканер для канала
    asyncio.create_task(auto_scanner_channel())
    
    print("✅ Бот запущен и готов к работе!")
    print("📡 Сканер арбитражных возможностей активен")
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
