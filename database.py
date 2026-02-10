import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Настройки по умолчанию
DEFAULT_SETTINGS = {
    'min_volume': 100,
    'min_profit': 5,
    'min_profit_pct': 3.0,
    'networks': ['BEP20', 'TRC20'],
    'brokers': ['KuCoin', 'Bybit'],
    'subscription_days': 0,
    'total_scans': 0,
    'username': 'User'
}

def init_db():
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            settings TEXT,
            subscription_days INTEGER DEFAULT 0,
            subscription_end TEXT,
            total_scans INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_scan TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            payment_id TEXT,
            amount REAL,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def get_user_settings(user_id: int) -> Dict[str, Any]:
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT settings, subscription_days, username, total_scans FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        settings = json.loads(result[0]) if result[0] else {}
        username = result[2] or f'User{user_id}'
        total_scans = result[3] or 0
        subscription_days = result[1] or 0
        
        # Объединяем настройки: сначала дефолтные, потом из БД
        user_settings = DEFAULT_SETTINGS.copy()
        user_settings.update(settings)
        user_settings.update({
            'username': username,
            'total_scans': total_scans,
            'subscription_days': subscription_days
        })
        
        return user_settings
    else:
        # Новый пользователь
        new_user_settings = DEFAULT_SETTINGS.copy()
        new_user_settings['username'] = f'User{user_id}'
        save_user_settings(user_id, new_user_settings)
        return new_user_settings

def save_user_settings(user_id: int, settings: Dict[str, Any]):
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    # Извлекаем поля для сохранения
    username = settings.get('username', f'User{user_id}')
    subscription_days = settings.get('subscription_days', 0)
    total_scans = settings.get('total_scans', 0)
    
    # Убираем поля, которые сохраняем отдельно
    settings_to_save = settings.copy()
    for field in ['username', 'subscription_days', 'total_scans']:
        settings_to_save.pop(field, None)
    
    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, username, settings, subscription_days, total_scans) 
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, json.dumps(settings_to_save), subscription_days, total_scans))
    
    conn.commit()
    conn.close()

def add_subscription_days(user_id: int, days: int):
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users SET subscription_days = subscription_days + ?
        WHERE user_id = ?
    ''', (days, user_id))
    
    conn.commit()
    conn.close()

def increment_scan_count(user_id: int):
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users SET total_scans = total_scans + 1, last_scan = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (user_id,))
    
    conn.commit()
    conn.close()

def save_payment(user_id: int, payment_id: str, amount: float, status: str = 'pending'):
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO payments (user_id, payment_id, amount, status)
        VALUES (?, ?, ?, ?)
    ''', (user_id, payment_id, amount, status))
    
    conn.commit()
    conn.close()

def get_payment_status(payment_id: str) -> Dict[str, Any]:
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM payments WHERE payment_id = ?', (payment_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'id': result[0],
            'user_id': result[1],
            'payment_id': result[2],
            'amount': result[3],
            'status': result[4],
            'created_at': result[5]
        }
    return {}

def update_payment_status(payment_id: str, status: str):
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE payments SET status = ?
        WHERE payment_id = ?
    ''', (status, payment_id))
    
    conn.commit()
    conn.close()

def get_active_users_count() -> int:
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE subscription_days > 0')
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else 0

def get_total_scans() -> int:
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT SUM(total_scans) FROM users')
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result and result[0] else 0

def get_all_users(limit: int = 100) -> List[Dict[str, Any]]:
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, username, subscription_days, total_scans, last_scan
        FROM users 
        ORDER BY last_scan DESC 
        LIMIT ?
    ''', (limit,))
    
    users = []
    for row in cursor.fetchall():
        users.append({
            'user_id': row[0],
            'username': row[1],
            'subscription_days': row[2],
            'total_scans': row[3],
            'last_scan': row[4]
        })
    
    conn.close()
    return users

# Инициализация БД при импорте
init_db()
