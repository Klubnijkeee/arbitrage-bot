import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
MIN_PROFIT = float(os.getenv('MIN_PROFIT', 0.8))
CHECK_INTERVAL = 30  # секунд