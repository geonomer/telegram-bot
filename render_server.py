# render_server.py
from flask import Flask
import os
import subprocess
import sys
import time

app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health():
    return "Bot is running!", 200

if __name__ == '__main__':
    # Получаем порт из переменной окружения Render
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Starting Flask server on port {port}...")
    
    # Запускаем основного бота в отдельном процессе
    # (предполагаем, что файл бота называется bot.py)
    print("🚀 Launching Telegram bot process...")
    subprocess.Popen([sys.executable, "bot.py"])
    
    # Даём боту секунду на запуск
    time.sleep(2)
    print("✅ Telegram bot process started. Flask server is now running.")
    
    # Запускаем Flask-сервер (он будет работать вечно)
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
