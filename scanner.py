import ccxt
import time
import os
import random
from typing import Dict, List, Tuple
from config import EXCHANGE_LINKS

class ArbitrageScanner:
    def __init__(self):
        self.exchanges = {
            'kucoin': ccxt.kucoin({'enableRateLimit': True, 'timeout': 20000}),
            'bybit': ccxt.bybit({'enableRateLimit': True, 'timeout': 20000, 'options': {'defaultType': 'spot'}}),
            'okx': ccxt.okx({'enableRateLimit': True, 'timeout': 20000}),
            'gateio': ccxt.gateio({'enableRateLimit': True, 'timeout': 20000}),
            'htx': ccxt.htx({'enableRateLimit': True, 'timeout': 20000})
        }
        self.markets = {}
        self.common_symbols = set()
    
    def load_markets(self):
        print("🔄 Loading markets...")
        for name, exchange in self.exchanges.items():
            try:
                exchange.load_markets()
                self.markets[name] = self._extract_symbols(exchange)
                print(f"✅ {name.capitalize()}: {len(self.markets[name])} pairs")
            except Exception as e:
                print(f"⚠️ {name}: {e}")
        
        self.common_symbols = self._find_common_symbols()
        print(f"🔗 {len(self.common_symbols)} common pairs")
    
    def _extract_symbols(self, exchange):
        symbols = {}
        for symbol, market in exchange.markets.items():
            if market['spot'] and market['quote'] == 'USDT':
                symbols[symbol] = symbol.replace('/', '-').upper()
        return symbols
    
    def _find_common_symbols(self):
        if len(self.markets) < 2:
            return set(['BTC/USDT', 'ETH/USDT'])
        all_symbols = [set(m.keys()) for m in self.markets.values()]
        return set.intersection(*all_symbols) if all_symbols else set()
    
    def get_price_safe(self, exchange, symbol: str) -> float:
        try:
            ticker = exchange.fetch_ticker(symbol)
            return float(ticker.get('last') or ticker.get('ask') or 0)
        except:
            return 0
    
    def find_arbitrage(self, min_volume: float = 100, min_profit: float = 5, min_pct: float = 3.0) -> List[Dict]:
        opportunities = []
        symbols = list(self.common_symbols)[:20]  # Топ-20
        
        for symbol in symbols:
            prices = {}
            for exch_name, exchange in self.exchanges.items():
                if symbol in self.markets.get(exch_name, {}):
                    price = self.get_price_safe(exchange, symbol)
                    if price > 0:
                        prices[exch_name.capitalize()] = price
            
            if len(prices) >= 2:
                sorted_prices = sorted(prices.items(), key=lambda x: x[1])
                buy_exch, buy_price = sorted_prices[0]
                sell_exch, sell_price = sorted_prices[-1]
                
                profit_pct = ((sell_price - buy_price) / buy_price * 100) - 0.4  # комиссии
                profit_usd = (min_volume / buy_price) * (sell_price - buy_price) * 0.98  # после комиссий
                
                if profit_usd >= min_profit and profit_pct >= min_pct:
                    opportunities.append({
                        'symbol': symbol.replace('/USDT', ''),
                        'buy_exchange': buy_exch,
                        'buy_price': buy_price,
                        'sell_exchange': sell_exch,
                        'sell_price': sell_price,
                        'profit_usd': profit_usd,
                        'profit_pct': profit_pct,
                        'volume': min_volume
                    })
        
        return sorted(opportunities, key=lambda x: x['profit_pct'], reverse=True)[:3]
    
    def format_signal(self, opp: Dict, network: str = 'BEP20') -> str:
        symbol = opp['symbol'].upper()
        buy_link = EXCHANGE_LINKS[opp['buy_exchange']].format(symbol)
        sell_link = EXCHANGE_LINKS[opp['sell_exchange']].format(symbol.lower())
        
        # Рассчет количества монет
        coins = opp['volume'] / opp['buy_price']
        coins_after_fee = coins * 0.996  # комиссия вывода ~0.4%
        profit_coins = coins_after_fee * (opp['sell_price'] / opp['buy_price']) * 0.998  # продажа с комиссией
        
        buy_value = coins * opp['buy_price']
        sell_value = profit_coins * opp['sell_price']
        
        return f"""👁‍🗨{opp['buy_exchange']} ({buy_link}) -> {opp['sell_exchange']} ({sell_link}) ({symbol})

↘️{opp['buy_exchange']} BUY ({buy_link}) 👉🏻 #{symbol}
💰Цена: {opp['buy_price']:.6f} USDT
💎Монет: {coins:,.0f} {symbol} = {buy_value:.1f} USDT

💳Комиссия вывода
💎{coins - coins_after_fee:.0f} {symbol} = {coins * opp['buy_price'] * 0.004:.1f} USDT

➡️{opp['sell_exchange']} SELL ({sell_link}) 👉🏻 #{symbol}
💰Цена: {opp['sell_price']:.6f} USDT
💎Монет: {coins_after_fee:,.0f} {symbol} = {sell_value:.1f} USDT

💰Профит: {opp['profit_usd']:.1f} USDT
🚩Доход: {opp['profit_pct']:.1f}%

Вывод: 🔀 {network}
Ввод: 🔀 {network}"""
