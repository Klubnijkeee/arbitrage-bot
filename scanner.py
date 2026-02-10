import ccxt
import time
import os
from typing import Dict, List

class ArbitrageScanner:
    def __init__(self):
        # Используем KuCoin вместо Binance (меньше блокирует)
        self.kucoin = ccxt.kucoin({
            'enableRateLimit': True,
            'timeout': 10000,
        })
        
        self.bybit = ccxt.bybit({
            'enableRateLimit': True,
            'timeout': 10000,
        })
        
        # Можно добавить другие биржи
        self.okx = ccxt.okx({
            'enableRateLimit': True,
            'timeout': 10000,
        })
        
        self.markets = {}
    
    def load_markets(self):
        """Загружаем торговые пары"""
        try:
            print("Loading KuCoin markets...")
            self.kucoin.load_markets()
            print("Loading Bybit markets...")
            self.bybit.load_markets()
            print("Loading OKX markets...")
            self.okx.load_markets()
            
            # Фильтруем USDT пары (без фьючерсов)
            self.markets['kucoin'] = {
                s: m['symbol'] for s, m in self.kucoin.markets.items() 
                if m['quote'] == 'USDT' and not m['future'] and not m['swap']
            }
            
            self.markets['bybit'] = {
                s: m['symbol'] for s, m in self.bybit.markets.items() 
                if m['quote'] == 'USDT' and not m['future'] and not m['swap']
            }
            
            self.markets['okx'] = {
                s: m['symbol'] for s, m in self.okx.markets.items() 
                if m['quote'] == 'USDT' and not m['future'] and not m['swap']
            }
            
            print(f"Loaded: {len(self.markets['kucoin'])} KuCoin, {len(self.markets['bybit'])} Bybit pairs")
            
        except Exception as e:
            print(f"Error loading markets: {e}")
            # Если не получилось загрузить, используем топ-20 популярных пар
            self.markets['kucoin'] = {
                'BTC/USDT': 'BTC/USDT',
                'ETH/USDT': 'ETH/USDT',
                'SOL/USDT': 'SOL/USDT',
                'BNB/USDT': 'BNB/USDT',
                'ADA/USDT': 'ADA/USDT',
                'XRP/USDT': 'XRP/USDT',
                'DOGE/USDT': 'DOGE/USDT',
                'DOT/USDT': 'DOT/USDT',
                'AVAX/USDT': 'AVAX/USDT',
                'MATIC/USDT': 'MATIC/USDT',
                'LINK/USDT': 'LINK/USDT',
                'UNI/USDT': 'UNI/USDT',
                'ATOM/USDT': 'ATOM/USDT',
                'LTC/USDT': 'LTC/USDT',
                'TRX/USDT': 'TRX/USDT',
                'NEAR/USDT': 'NEAR/USDT',
                'ALGO/USDT': 'ALGO/USDT',
                'FIL/USDT': 'FIL/USDT',
                'ETC/USDT': 'ETC/USDT',
                'XLM/USDT': 'XLM/USDT'
            }
            self.markets['bybit'] = self.markets['kucoin'].copy()
            self.markets['okx'] = self.markets['kucoin'].copy()
    
    def get_price(self, exchange: ccxt.Exchange, symbol: str) -> float:
        """Получаем цену пары"""
        try:
            ticker = exchange.fetch_ticker(symbol)
            return float(ticker['last']) if ticker['last'] else 0
        except Exception as e:
            print(f"Error getting price for {symbol}: {e}")
            return 0
    
    def find_arbitrage(self) -> List[Dict]:
        """ИЩЕМ АРБИТРАЖ! 🔥"""
        opportunities = []
        
        # Берем общие пары между KuCoin и Bybit
        common_symbols = list(
            set(self.markets['kucoin'].keys()) & 
            set(self.markets['bybit'].keys())
        )[:30]  # ограничиваем для скорости
        
        # Добавляем OKX для сравнения
        okx_symbols = list(self.markets['okx'].keys())[:30]
        
        print(f"Scanning {len(common_symbols)} common symbols...")
        
        MIN_PROFIT = float(os.getenv('MIN_PROFIT', 0.8))
        
        for symbol in common_symbols:
            try:
                # Цены с разных бирж
                kucoin_price = self.get_price(self.kucoin, symbol)
                bybit_price = self.get_price(self.bybit, symbol)
                
                # Проверяем OKX если есть
                okx_price = 0
                if symbol in self.markets['okx']:
                    okx_price = self.get_price(self.okx, symbol)
                
                if kucoin_price > 0 and bybit_price > 0:
                    # Находим лучшую цену покупки и продажи
                    prices = {
                        'KuCoin': kucoin_price,
                        'Bybit': bybit_price,
                    }
                    
                    if okx_price > 0:
                        prices['OKX'] = okx_price
                    
                    # Сортируем цены
                    sorted_prices = sorted(prices.items(), key=lambda x: x[1])
                    buy_exchange, buy_price = sorted_prices[0]  # самая низкая цена
                    sell_exchange, sell_price = sorted_prices[-1]  # самая высокая цена
                    
                    # Рассчитываем профит (минус 0.2% комиссии)
                    profit_pct = ((sell_price - buy_price) / buy_price) * 100
                    
                    # Вычитаем примерные комиссии (0.1% на каждой бирже)
                    profit_pct -= 0.2
                    
                    if profit_pct >= MIN_PROFIT:
                        opportunities.append({
                            'symbol': symbol,
                            'buy_exchange': buy_exchange,
                            'buy_price': buy_price,
                            'sell_exchange': sell_exchange,
                            'sell_price': sell_price,
                            'profit_pct': round(profit_pct, 2),
                            'timestamp': time.strftime('%H:%M:%S'),
                            'all_prices': prices
                        })
                        
            except Exception as e:
                print(f"Error scanning {symbol}: {e}")
                continue
        
        # Сортируем по убыванию профита
        opportunities.sort(key=lambda x: x['profit_pct'], reverse=True)
        
        # Логируем результаты
        if opportunities:
            print(f"Found {len(opportunities)} opportunities. Best: {opportunities[0]['profit_pct']}%")
        else:
            print("No arbitrage opportunities found")
        
        return opportunities[:10]  # возвращаем топ-10
