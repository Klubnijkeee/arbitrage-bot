import ccxt
import time
import os
import random
from typing import Dict, List, Set

class ArbitrageScanner:
    def __init__(self):
        # Биржи, которые хорошо работают из Европы
        self.kucoin = ccxt.kucoin({
            'enableRateLimit': True,
            'timeout': 20000,
        })
        
        self.bybit = ccxt.bybit({
            'enableRateLimit': True,
            'timeout': 20000,
            'options': {
                'defaultType': 'spot',  # Важно! Используем спотовые пары
            }
        })
        
        self.okx = ccxt.okx({
            'enableRateLimit': True,
            'timeout': 20000,
        })
        
        # Резервная биржа на случай блокировок
        self.gateio = ccxt.gateio({
            'enableRateLimit': True,
            'timeout': 20000,
        })
        
        self.markets = {}
        self.common_symbols = set()
    
    def load_markets(self):
        """Загружаем и анализируем торговые пары с бирж"""
        print("🔄 Loading markets from exchanges...")
        
        loaded_exchanges = []
        
        try:
            # Пытаемся загрузить KuCoin
            self.kucoin.load_markets()
            kucoin_symbols = self._extract_spot_symbols(self.kucoin, 'KuCoin')
            if kucoin_symbols:
                self.markets['kucoin'] = kucoin_symbols
                loaded_exchanges.append('KuCoin')
                print(f"✅ KuCoin: {len(kucoin_symbols)} spot pairs")
        except Exception as e:
            print(f"⚠️ Failed to load KuCoin markets: {e}")
        
        try:
            # Пытаемся загрузить Bybit
            self.bybit.load_markets()
            bybit_symbols = self._extract_spot_symbols(self.bybit, 'Bybit')
            if bybit_symbols:
                self.markets['bybit'] = bybit_symbols
                loaded_exchanges.append('Bybit')
                print(f"✅ Bybit: {len(bybit_symbols)} spot pairs")
        except Exception as e:
            print(f"⚠️ Failed to load Bybit markets: {e}")
        
        try:
            # Пытаемся загрузить OKX
            self.okx.load_markets()
            okx_symbols = self._extract_spot_symbols(self.okx, 'OKX')
            if okx_symbols:
                self.markets['okx'] = okx_symbols
                loaded_exchanges.append('OKX')
                print(f"✅ OKX: {len(okx_symbols)} spot pairs")
        except Exception as e:
            print(f"⚠️ Failed to load OKX markets: {e}")
        
        try:
            # Пытаемся загрузить Gate.io (резерв)
            self.gateio.load_markets()
            gateio_symbols = self._extract_spot_symbols(self.gateio, 'Gate.io')
            if gateio_symbols:
                self.markets['gateio'] = gateio_symbols
                loaded_exchanges.append('Gate.io')
                print(f"✅ Gate.io: {len(gateio_symbols)} spot pairs")
        except Exception as e:
            print(f"⚠️ Failed to load Gate.io markets: {e}")
        
        # Находим общие пары между биржами
        self._find_common_symbols()
        
        print(f"📊 Loaded {len(loaded_exchanges)} exchanges: {', '.join(loaded_exchanges)}")
        print(f"🔗 Found {len(self.common_symbols)} common trading pairs")
        
        # Если не удалось загрузить ни одной биржи, используем запасной список
        if not self.common_symbols:
            print("🚨 No common symbols found, using backup list...")
            self._use_backup_symbols()
    
    def _extract_spot_symbols(self, exchange, exchange_name: str) -> Dict[str, str]:
        """Извлекаем спотовые USDT пары из биржи"""
        symbols = {}
        
        try:
            for market_id, market in exchange.markets.items():
                # Проверяем что это спотовая пара (не фьючерс, не своп)
                if (market.get('spot', False) or 
                    (not market.get('future', True) and 
                     not market.get('swap', False) and
                     not market.get('option', False))):
                    
                    # Берем только USDT пары
                    if (market.get('quote') == 'USDT' or 
                        market.get('settle') == 'USDT' or
                        (market.get('symbol') and '/USDT' in market['symbol'])):
                        
                        # Используем стандартизированный символ
                        symbol = market['symbol']
                        symbols[symbol] = symbol
            
            # Логируем топ-5 символов для отладки
            if symbols:
                top_symbols = list(symbols.keys())[:5]
                print(f"   {exchange_name} top symbols: {', '.join(top_symbols)}")
                
        except Exception as e:
            print(f"   Error extracting {exchange_name} symbols: {e}")
        
        return symbols
    
    def _find_common_symbols(self):
        """Находим общие символы между всеми загруженными биржами"""
        if not self.markets:
            return
        
        # Собираем все символы со всех бирж
        all_symbol_sets = []
        for exchange, symbols in self.markets.items():
            if symbols:
                all_symbol_sets.append(set(symbols.keys()))
        
        # Находим пересечение между всеми биржами
        if all_symbol_sets:
            self.common_symbols = set.intersection(*all_symbol_sets)
            
            # Если пересечение слишком маленькое, берем общие для хотя бы 2 бирж
            if len(self.common_symbols) < 10:
                print("⚠️ Few common symbols, looking for pairs common to at least 2 exchanges...")
                self.common_symbols = set()
                all_symbols = {}
                
                # Считаем в скольких биржах есть каждый символ
                for symbols_set in all_symbol_sets:
                    for symbol in symbols_set:
                        all_symbols[symbol] = all_symbols.get(symbol, 0) + 1
                
                # Берем символы, которые есть хотя бы в 2 биржах
                self.common_symbols = {symbol for symbol, count in all_symbols.items() if count >= 2}
    
    def _use_backup_symbols(self):
        """Используем запасной список популярных пар"""
        backup_symbols = [
            'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT',
            'XRP/USDT', 'ADA/USDT', 'AVAX/USDT', 'DOGE/USDT',
            'DOT/USDT', 'MATIC/USDT', 'LINK/USDT', 'TRX/USDT',
            'UNI/USDT', 'LTC/USDT', 'ATOM/USDT', 'ETC/USDT',
            'XLM/USDT', 'NEAR/USDT', 'ALGO/USDT', 'FIL/USDT'
        ]
        
        self.common_symbols = set(backup_symbols)
        
        # Создаем фиктивные рынки для каждой биржи
        for exchange in ['kucoin', 'bybit', 'okx', 'gateio']:
            self.markets[exchange] = {s: s for s in backup_symbols}
        
        print(f"📋 Using backup list: {len(backup_symbols)} popular pairs")
    
    def get_price_safe(self, exchange, symbol: str) -> float:
        """Безопасное получение цены с обработкой ошибок"""
        try:
            ticker = exchange.fetch_ticker(symbol)
            
            # Проверяем разные поля с ценой
            price_fields = ['last', 'ask', 'bid', 'close', 'average']
            for field in price_fields:
                price = ticker.get(field)
                if price is not None and price > 0:
                    return float(price)
            
            return 0.0
        except Exception as e:
            # Слишком много логов загромождают вывод
            return 0.0
    
    def find_arbitrage(self) -> List[Dict]:
        """Поиск арбитражных возможностей"""
        opportunities = []
        MIN_PROFIT = float(os.getenv('MIN_PROFIT', 0.8))
        
        # Преобразуем в список и ограничиваем количество для скорости
        symbols_to_check = list(self.common_symbols)
        
        # Если символов много, берем случайную выборку
        if len(symbols_to_check) > 30:
            symbols_to_check = random.sample(symbols_to_check, 30)
        
        print(f"🔍 Scanning {len(symbols_to_check)} common pairs...")
        
        for symbol in symbols_to_check:
            try:
                prices = {}
                exchanges_data = []
                
                # Получаем цены со всех доступных бирж
                if 'kucoin' in self.markets and symbol in self.markets['kucoin']:
                    price = self.get_price_safe(self.kucoin, symbol)
                    if price > 0:
                        prices['KuCoin'] = price
                        exchanges_data.append(('KuCoin', price))
                
                if 'bybit' in self.markets and symbol in self.markets['bybit']:
                    price = self.get_price_safe(self.bybit, symbol)
                    if price > 0:
                        prices['Bybit'] = price
                        exchanges_data.append(('Bybit', price))
                
                if 'okx' in self.markets and symbol in self.markets['okx']:
                    price = self.get_price_safe(self.okx, symbol)
                    if price > 0:
                        prices['OKX'] = price
                        exchanges_data.append(('OKX', price))
                
                if 'gateio' in self.markets and symbol in self.markets['gateio']:
                    price = self.get_price_safe(self.gateio, symbol)
                    if price > 0:
                        prices['Gate.io'] = price
                        exchanges_data.append(('Gate.io', price))
                
                # Нужно минимум 2 цены от разных бирж
                if len(prices) >= 2:
                    # Сортируем по цене
                    exchanges_data.sort(key=lambda x: x[1])
                    
                    buy_exchange, buy_price = exchanges_data[0]
                    sell_exchange, sell_price = exchanges_data[-1]
                    
                    # Рассчитываем профит (минус комиссии 0.2%)
                    profit_pct = ((sell_price - buy_price) / buy_price) * 100 - 0.2
                    
                    if profit_pct >= MIN_PROFIT:
                        opportunities.append({
                            'symbol': symbol,
                            'buy_exchange': buy_exchange,
                            'buy_price': buy_price,
                            'sell_exchange': sell_exchange,
                            'sell_price': sell_price,
                            'profit_pct': round(profit_pct, 2),
                            'timestamp': time.strftime('%H:%M:%S'),
                            'demo': False,
                            'num_exchanges': len(prices)
                        })
                        
            except Exception as e:
                # Тихий пропуск ошибок
                continue
        
        # Если реального арбитража нет, генерируем демо-данные
        if not opportunities:
            opportunities = self._generate_demo_opportunities()
        
        # Сортируем по убыванию профита
        opportunities.sort(key=lambda x: x['profit_pct'], reverse=True)
        
        if opportunities:
            best_profit = opportunities[0]['profit_pct']
            demo_count = sum(1 for opp in opportunities if opp.get('demo', False))
            real_count = len(opportunities) - demo_count
            
            print(f"✅ Found {real_count} real + {demo_count} demo opportunities")
            print(f"🏆 Best profit: {best_profit}%")
        else:
            print("📊 No opportunities found")
        
        return opportunities[:5]  # возвращаем топ-5
    
    def _generate_demo_opportunities(self) -> List[Dict]:
        """Генерируем демо-возможности для теста"""
        opportunities = []
        
        # Берем случайные символы из общего списка
        if self.common_symbols:
            symbols = random.sample(list(self.common_symbols), min(3, len(self.common_symbols)))
        else:
            symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
        
        for symbol in symbols:
            # Базовые цены в зависимости от символа
            if 'BTC' in symbol:
                base_price = 50000 + random.uniform(-2000, 2000)
            elif 'ETH' in symbol:
                base_price = 3000 + random.uniform(-150, 150)
            else:
                base_price = 100 + random.uniform(-20, 20)
            
            # Генерируем реалистичный арбитраж (0.8-2.5%)
            profit = random.uniform(0.8, 2.5)
            
            # Случайные биржи
            all_exchanges = ['KuCoin', 'Bybit', 'OKX', 'Gate.io']
            buy_exchange = random.choice(all_exchanges)
            sell_exchange = random.choice([e for e in all_exchanges if e != buy_exchange])
            
            opportunities.append({
                'symbol': symbol,
                'buy_exchange': buy_exchange,
                'buy_price': round(base_price, 2),
                'sell_exchange': sell_exchange,
                'sell_price': round(base_price * (1 + profit/100), 2),
                'profit_pct': round(profit, 2),
                'timestamp': time.strftime('%H:%M:%S'),
                'demo': True
            })
        
        return opportunities
