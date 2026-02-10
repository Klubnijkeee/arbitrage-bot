import os
from dotenv import load_dotenv
from typing import Dict, List

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID', '@arbitrage_signals')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))  # Твой Telegram ID

# Настройки по умолчанию
DEFAULT_SETTINGS = {
    'min_volume': 100,      # USDT
    'min_profit': 5,        # USDT
    'min_profit_pct': 3.0,  # %
    'networks': ['BEP20', 'TRC20', 'ERC20'],  # Активные сети
    'brokers': ['KuCoin', 'Bybit', 'OKX', 'Gate.io', 'HTX'],  # Активные биржи
    'subscription_days': 0,  # Дней подписки осталось
    'user_volume': {}       # Индивидуальные объемы {user_id: volume}
}

# Ссылки на торговые пары
EXCHANGE_LINKS = {
    'KuCoin': 'https://www.kucoin.com/ru/trade/{}-{USDT}',
    'Bybit': 'https://www.bybit.com/ru-RU/trade/spot/{}/USDT',
    'OKX': 'https://www.okx.com/ru/trade-spot/{}-USDT',
    'Gate.io': 'https://www.gate.io/trade/{}_USDT',
    'HTX': 'https://www.htx.com/en-us/trade/{}_usdt'
}
