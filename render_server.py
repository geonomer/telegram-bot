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
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Starting Flask server on port {port}...")
    subprocess.Popen([sys.executable, "bot.py"])
    time.sleep(2)
    print("✅ Telegram bot process started. Flask server is now running.")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
