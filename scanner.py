import ccxt
import time
from typing import Dict, List, Tuple

class ArbitrageScanner:
    def __init__(self):
        self.binance = ccxt.binance({'enableRateLimit': True})
        self.bybit = ccxt.bybit({'enableRateLimit': True})
        self.markets = {}
    
    def load_markets(self):
        """Загружаем торговые пары"""
        self.binance.load_markets()
        self.bybit.load_markets()
        self.markets['binance'] = {s: m['symbol'] for s, m in self.binance.markets.items() if '/USDT:' in m['symbol']}
        self.markets['bybit'] = {s: m['symbol'] for s, m in self.bybit.markets.items() if '/USDT:' in m['symbol']}
    
    def get_price(self, exchange: ccxt.Exchange, symbol: str) -> float:
        """Получаем цену пары"""
        try:
            ticker = exchange.fetch_ticker(symbol)
            return float(ticker['last'])
        except:
            return 0
    
    def find_arbitrage(self) -> List[Dict]:
        """ИЩЕМ АРБИТРАЖ! 🔥"""
        opportunities = []
        
        # Пересекающиеся пары
        common_symbols = list(set(self.markets['binance'].keys()) & set(self.markets['bybit'].keys()))[:50]  # топ-50
        
        for symbol in common_symbols:
            try:
                # Цены
                binance_price = self.get_price(self.binance, self.markets['binance'][symbol])
                bybit_price = self.get_price(self.bybit, self.markets['bybit'][symbol])
                
                if binance_price > 0 and bybit_price > 0:
                    # Процент разницы
                    diff_pct = abs(binance_price - bybit_price) / min(binance_price, bybit_price) * 100
                    
                    if diff_pct >= float(os.getenv('MIN_PROFIT', 0.8)):
                        profit = (max(binance_price, bybit_price) - min(binance_price, bybit_price)) / min(binance_price, bybit_price) * 100 - 0.18  # минус комиссии
                        
                        opportunities.append({
                            'symbol': symbol,
                            'binance_price': binance_price,
                            'bybit_price': bybit_price,
                            'diff_pct': diff_pct,
                            'profit_pct': profit,
                            'timestamp': time.strftime('%H:%M:%S')
                        })
            except Exception as e:
                continue
        
        return sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)