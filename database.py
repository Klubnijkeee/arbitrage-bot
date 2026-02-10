import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List

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
        return {
            **DEFAULT_SETTINGS,
            **settings,
            'subscription_days': result[1],
            'username': result[3] or 'User',
            'total_scans': result[2] or 0
        }
    else:
        save_user_settings(user_id, {})
        return get_user_settings(user_id)

def save_user_settings(user_id: int, settings: Dict[str, Any]):
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, settings, total_scans)
        VALUES (?, ?, ?, COALESCE((SELECT total_scans FROM users WHERE user_id = ?), 0))
    ''', (user_id, settings.get('username', ''), json.dumps(settings), user_id))
    
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

init_db()
