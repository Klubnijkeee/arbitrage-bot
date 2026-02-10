import sqlite3
import json
from typing import Dict, Any
from config import DEFAULT_SETTINGS

def init_db():
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            settings TEXT,
            subscription_days INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def get_user_settings(user_id: int) -> Dict[str, Any]:
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT settings, subscription_days FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        settings = json.loads(result[0]) if result[0] else DEFAULT_SETTINGS
        settings['subscription_days'] = result[1]
        return settings
    else:
        # Новый пользователь
        save_user_settings(user_id, DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS

def save_user_settings(user_id: int, settings: Dict[str, Any]):
    conn = sqlite3.connect('arbitrage_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, settings, subscription_days)
        VALUES (?, ?, ?, ?)
    ''', (user_id, '', json.dumps(settings), settings.get('subscription_days', 0)))
    
    conn.commit()
    conn.close()

# Инициализация БД
init_db()
