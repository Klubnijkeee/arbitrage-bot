import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID', '@arbitrage_signals')
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip().isdigit()]
NOWPAYMENTS_API_KEY = os.getenv('NOWPAYMENTS_API_KEY')
SUBSCRIPTION_PRICE = float(os.getenv('SUBSCRIPTION_PRICE', 50))

DEFAULT_SETTINGS = {
    'min_volume': 100,
    'min_profit': 5,
    'min_profit_pct': 3.0,
    'networks': ['BEP20', 'TRC20', 'ERC20'],
    'brokers': ['KuCoin', 'Bybit', 'OKX', 'Gate.io', 'HTX']
}

EXCHANGE_LINKS = {
    'KuCoin': 'https://www.kucoin.com/ru/trade/{}-USDT',
    'Bybit': 'https://www.bybit.com/ru-RU/trade/spot/{}/USDT',
    'OKX': 'https://www.okx.com/ru/trade-spot/{}-USDT',
    'Gate.io': 'https://www.gate.io/trade/{}_USDT',
    'HTX': 'https://www.htx.com/en-us/trade/{}_usdt'
}
