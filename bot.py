# -*- coding: utf-8 -*-
import asyncio
import random
import string
import os
import re
import sqlite3
import atexit
import base64
import requests
import threading
import time
import shutil
import sys
import fcntl
import signal
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import LabeledPrice, PreCheckoutQuery, SuccessfulPayment
from pyrogram import Client
from pyrogram.errors import PhoneNumberInvalid, AuthKeyUnregistered, FloodWait
from pyrogram.enums import ChatType

# ================== ПРЕДОТВРАЩЕНИЕ ДВОЙНОГО ЗАПУСКА ==================
def prevent_multiple_instances():
    """Предотвращает запуск нескольких экземпляров бота"""
    lock_file = '/tmp/bot.lock'
    try:
        with open(lock_file, 'w') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                f.write(str(os.getpid()))
                f.flush()
                print(f"✅ Lock-файл создан. PID: {os.getpid()}")
                def remove_lock(signum=None, frame=None):
                    try:
                        fcntl.flock(f, fcntl.LOCK_UN)
                        os.unlink(lock_file)
                        print("✅ Lock-файл удален")
                    except: pass
                    sys.exit(0)
                signal.signal(signal.SIGTERM, remove_lock)
                signal.signal(signal.SIGINT, remove_lock)
                return True
            except IOError:
                print("❌ Бот уже запущен! Завершаем работу.")
                return False
    except Exception as e:
        print(f"❌ Ошибка при создании lock-файла: {e}")
        return True

if not prevent_multiple_instances():
    sys.exit(1)

# ================== ПРОВЕРКА БАЗЫ ДАННЫХ ==================
def fix_corrupted_db():
    """Проверяет и исправляет поврежденную базу данных"""
    print("\n🔧 ПРОВЕРКА ЦЕЛОСТНОСТИ БАЗЫ ДАННЫХ:")
    os.makedirs("sessions", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    db_path = "data/bot.db"
    if os.environ.get('RESET_DB') == 'true':
        print("🗑️ Принудительное удаление базы по RESET_DB")
        if os.path.exists(db_path): os.remove(db_path)
        if os.path.exists("data/bot.db.backup"): os.remove("data/bot.db.backup")
    if os.path.exists(db_path):
        size = os.path.getsize(db_path)
        print(f"📊 Размер файла БД: {size} байт")
        try:
            test_conn = sqlite3.connect(db_path)
            test_cursor = test_conn.cursor()
            test_cursor.execute("PRAGMA integrity_check")
            result = test_cursor.fetchone()
            test_conn.close()
            if result and result[0] == "ok":
                print("✅ База данных в порядке")
                return True
            else:
                print("❌ База данных повреждена!")
        except Exception as e:
            print(f"❌ Ошибка при проверке: {e}")
        backup_path = "data/bot.db.backup"
        if os.path.exists(backup_path):
            print("🔄 Найден бэкап, восстанавливаем...")
            try:
                test_conn = sqlite3.connect(backup_path)
                test_conn.close()
                shutil.copy2(backup_path, db_path)
                print("✅ База восстановлена из бэкапа")
                return True
            except Exception as e:
                print(f"❌ Ошибка при восстановлении из бэкапа: {e}")
        print("🆕 Создаем новую базу данных...")
        try:
            if os.path.exists(db_path):
                corrupted_path = f"data/bot.db.corrupted_{int(time.time())}"
                os.rename(db_path, corrupted_path)
                print(f"📦 Поврежденная база сохранена как {corrupted_path}")
            new_conn = sqlite3.connect(db_path)
            new_conn.close()
            print("✅ Новая база данных создана")
            return True
        except Exception as e:
            print(f"❌ Ошибка создания новой базы: {e}")
            return False
    else:
        print("🆕 Файл базы не существует, будет создан новый")
        return True
fix_corrupted_db()

# ================== ВОССТАНОВЛЕНИЕ БАЗЫ ИЗ ENV ==================
def restore_db_from_env():
    """Восстанавливает базу данных из переменных окружения"""
    print("\n🔍 ПРОВЕРКА БЭКАПА БАЗЫ ДАННЫХ:")
    db_backup = os.environ.get('DB_BACKUP')
    if db_backup:
        try:
            db_backup = db_backup.replace('\n', '').replace('\r', '').strip()
            db_data = base64.b64decode(db_backup)
            if os.path.exists("data/bot.db"):
                try:
                    test_conn = sqlite3.connect("data/bot.db")
                    test_conn.close()
                    shutil.copy2("data/bot.db", "data/bot.db.prev")
                    print("📦 Создана резервная копия текущей БД")
                except:
                    print("⚠️ Текущая БД повреждена, будет заменена")
            with open("data/bot.db", "wb") as f:
                f.write(db_data)
            print(f"✅ База данных восстановлена из бэкапа ({len(db_data)} байт)")
            return True
        except Exception as e:
            print(f"❌ Ошибка восстановления БД: {e}")
    print("🆕 Будет создана новая база данных")
    return False
restore_db_from_env()

# ================== ВОССТАНОВЛЕНИЕ СЕССИЙ ==================
def restore_sessions():
    """Восстанавливает файлы сессий из переменных окружения"""
    print("\n🔍 ПРОВЕРКА СЕССИЙ В ENV:")
    os.makedirs("sessions", exist_ok=True)
    restored = 0
    for i in range(1, 10):
        session_data = os.environ.get(f'SESSION_{i}')
        if session_data:
            try:
                session_data = session_data.replace('\n', '').replace('\r', '').strip()
                file_path = f'sessions/account_{i}.session'
                decoded = base64.b64decode(session_data)
                with open(file_path, 'wb') as f:
                    f.write(decoded)
                size = os.path.getsize(file_path)
                print(f"✅ Восстановлена сессия account_{i} ({size} байт)")
                restored += 1
            except Exception as e:
                print(f"❌ Ошибка восстановления session_{i}: {e}")
    print(f"✅ Восстановлено {restored} сессий из ENV")
    return restored

def check_sessions():
    print("\n🔍 ПРОВЕРКА ФАЙЛОВ СЕССИЙ:")
    try:
        files = os.listdir("sessions")
        print(f"📁 Файлов в папке sessions: {len(files)}")
        for f in files:
            file_path = os.path.join("sessions", f)
            size = os.path.getsize(file_path)
            print(f"  - {f} ({size} байт)")
    except Exception as e:
        print(f"❌ Ошибка при проверке папки sessions: {e}")
    print("=" * 50)
restore_sessions()
check_sessions()

# ================== ФУНКЦИЯ ПИНГА ==================
def self_ping():
    def ping():
        url = os.environ.get('RENDER_EXTERNAL_URL', 'https://telegram-bot.onrender.com').rstrip('/')
        health_url = f"{url}/health"
        while True:
            try:
                response = requests.get(health_url, timeout=5)
                print(f"✅ Self-ping successful at {time.strftime('%H:%M:%S')} - {response.status_code}")
            except: pass
            time.sleep(600)
    thread = threading.Thread(target=ping, daemon=True)
    thread.start()
    print("✅ Self-ping thread started")
self_ping()

# ================== HEALTH CHECK ==================
async def health_check(request):
    return web.Response(text="OK", status=200)
async def start_health_server():
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    print("✅ Health check server started on port 10000")
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()
asyncio.run_coroutine_threadsafe(start_health_server(), loop)

# ================== НАСТРОЙКИ ==================
TOKEN = os.environ.get('TOKEN', "8054814092:AAEVkB2fThqWSL_fwoNFZ7oQ7Dtjwr4wNt0")
ADMIN_ID = int(os.environ.get('ADMIN_ID', 5019414179))
API_ID = int(os.environ.get('API_ID', 37379476))
API_HASH = os.environ.get('API_HASH', "67cf40314dc0f31534b4b7feeae39242")

PRICE_STARS = 149
DISCOUNT_STARS = 50

# ================== НАСТРОЙКИ КАНАЛА ==================
REQUIRED_CHANNELS = [
    {
        "url": "https://t.me/Geo_Nomer_Store",
        "username": "@Geo_Nomer_Store",
        "name": "GeoNomer | Главный канал"
    }
]

FLAGS = { "us": "🇺🇸", "ru": "🇷🇺", "gb": "🇬🇧", "mm": "🇲🇲" }
EMOJI = {
    "success": "✅", "error": "❌", "wait": "⏳", "money": "💰",
    "star": "⭐", "phone": "📱", "referral": "👥", "support": "📞",
    "help": "❓", "back": "◀️", "code": "🔐", "warning": "⚠️",
    "crown": "👑", "chart": "📊", "time": "⏱️", "lock": "🔒",
    "unlock": "🔓", "discount": "🏷️", "payment": "💳", "link": "🔗",
    "info": "ℹ️", "star2": "✨", "copy": "📋", "arrow": "👉",
    "key": "🔑", "guard": "🛡️", "settings": "⚙️", "check": "✔️",
    "vpn": "🌐", "wait2": "⏰", "alert": "⚠️", "stats": "📊", "total": "📈"
}

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================== БАЗА ДАННЫХ ==================
class Database:
    def __init__(self):
        self.db_path = "data/bot.db"
        self.conn = None
        self.cursor = None
        self.max_retries = 3
        self.connect_with_retry()
        self.create_tables()
        self.migrate_database()
        print("✅ База данных SQLite инициализирована")

    def connect_with_retry(self):
        for attempt in range(self.max_retries):
            try:
                self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=20)
                self.conn.row_factory = sqlite3.Row
                self.cursor = self.conn.cursor()
                self.cursor.execute("PRAGMA integrity_check")
                result = self.cursor.fetchone()
                if result and result[0] == "ok":
                    print(f"✅ Подключение к БД успешно (попытка {attempt + 1})")
                    return True
                else:
                    raise sqlite3.DatabaseError("Database integrity check failed")
            except sqlite3.DatabaseError as e:
                print(f"❌ Ошибка БД (попытка {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    self.recover_database()
                    time.sleep(2)
                else:
                    self.create_new_database()
        return False

    def recover_database(self):
        print("🔄 Попытка восстановления базы данных...")
        backup_path = "data/bot.db.backup"
        if os.path.exists(backup_path):
            try:
                test_conn = sqlite3.connect(backup_path)
                test_conn.close()
                shutil.copy2(backup_path, self.db_path)
                print("✅ База восстановлена из бэкапа")
                return True
            except: pass
        try:
            corrupted_conn = sqlite3.connect(self.db_path)
            corrupted_conn.text_factory = bytes
            with open('data/dump.sql', 'w') as f:
                for line in corrupted_conn.iterdump():
                    try:
                        if isinstance(line, bytes):
                            line = line.decode('utf-8', errors='ignore')
                        f.write('%s\n' % line)
                    except: continue
            corrupted_conn.close()
            os.rename(self.db_path, self.db_path + ".old")
            new_conn = sqlite3.connect(self.db_path)
            with open('data/dump.sql', 'r') as f:
                new_conn.executescript(f.read())
            new_conn.close()
            print("✅ База восстановлена через SQL дамп")
            return True
        except Exception as e:
            print(f"❌ Ошибка восстановления: {e}")
            return False

    def create_new_database(self):
        print("🆕 Создание новой базы данных...")
        if os.path.exists(self.db_path):
            corrupted_path = f"data/bot.db.corrupted_{int(time.time())}"
            os.rename(self.db_path, corrupted_path)
            print(f"📦 Поврежденная база сохранена как {corrupted_path}")
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=20)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        print("✅ Новая база данных создана")

    def migrate_database(self):
        try:
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in self.cursor.fetchall()]
            if 'total_invited' not in columns:
                print("🔄 Добавляем поле total_invited в таблицу users...")
                self.cursor.execute('ALTER TABLE users ADD COLUMN total_invited INTEGER DEFAULT 0')
                self.conn.commit()
                print("✅ Поле total_invited добавлено")
                self.cursor.execute('UPDATE users SET total_invited = ref_count')
                self.conn.commit()
                print(f"✅ Обновлено {self.cursor.rowcount} записей")
        except Exception as e:
            print(f"⚠️ Ошибка при миграции: {e}")

    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                ref_code TEXT UNIQUE,
                ref_count INTEGER DEFAULT 0,
                discount INTEGER DEFAULT 0,
                discount_used INTEGER DEFAULT 0,
                discount_given INTEGER DEFAULT 0,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER UNIQUE,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                account_number TEXT,
                phone TEXT,
                price INTEGER,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_number TEXT UNIQUE,
                phone TEXT UNIQUE,
                country TEXT,
                country_name TEXT,
                api_id INTEGER,
                api_hash TEXT,
                session_file TEXT,
                description TEXT,
                in_use INTEGER DEFAULT 0,
                current_user INTEGER,
                purchase_date TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (current_user) REFERENCES users(user_id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                user_id INTEGER,
                action TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(account_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                account_id INTEGER PRIMARY KEY,
                session_data TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(account_id)
            )
        ''')
        self.conn.commit()

    # ----- Пользователи -----
    def add_user(self, user_id):
        try:
            for attempt in range(10):
                ref_code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                self.cursor.execute("SELECT user_id FROM users WHERE ref_code = ?", (ref_code,))
                if not self.cursor.fetchone():
                    break
            else:
                ref_code = f"user_{user_id}"
            self.cursor.execute('INSERT OR IGNORE INTO users (user_id, ref_code) VALUES (?, ?)', (user_id, ref_code))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка добавления пользователя {user_id}: {e}")
            return False

    def get_user(self, user_id):
        try:
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in self.cursor.fetchall()]
            if 'total_invited' in columns:
                self.cursor.execute('SELECT user_id, ref_code, ref_count, discount, discount_used, discount_given, total_invited FROM users WHERE user_id = ?', (user_id,))
                row = self.cursor.fetchone()
                if row:
                    return {
                        "user_id": row[0], "ref_code": row[1], "ref_count": row[2],
                        "discount": row[3], "discount_used": bool(row[4]), "discount_given": bool(row[5]),
                        "total_invited": row[6] or 0
                    }
            else:
                self.cursor.execute('SELECT user_id, ref_code, ref_count, discount, discount_used, discount_given FROM users WHERE user_id = ?', (user_id,))
                row = self.cursor.fetchone()
                if row:
                    return {
                        "user_id": row[0], "ref_code": row[1], "ref_count": row[2],
                        "discount": row[3], "discount_used": bool(row[4]), "discount_given": bool(row[5]),
                        "total_invited": row[2]
                    }
        except Exception as e:
            print(f"Ошибка получения пользователя {user_id}: {e}")
        return None

    # ----- Рефералы -----
    def add_referral(self, referrer_id, referred_id):
        try:
            if referrer_id == referred_id: return False
            self.cursor.execute("SELECT id FROM referrals WHERE referred_id = ?", (referred_id,))
            if self.cursor.fetchone(): return False
            self.cursor.execute('INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)', (referrer_id, referred_id))
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in self.cursor.fetchall()]
            if 'total_invited' in columns:
                self.cursor.execute('UPDATE users SET ref_count = ref_count + 1, total_invited = total_invited + 1 WHERE user_id = ?', (referrer_id,))
            else:
                self.cursor.execute('UPDATE users SET ref_count = ref_count + 1 WHERE user_id = ?', (referrer_id,))
            self.cursor.execute('SELECT ref_count FROM users WHERE user_id = ?', (referrer_id,))
            ref_count_row = self.cursor.fetchone()
            if ref_count_row and ref_count_row[0] >= 5:
                self.cursor.execute('UPDATE users SET discount = ?, discount_given = 1 WHERE user_id = ? AND discount_given = 0', (DISCOUNT_STARS, referrer_id))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка добавления реферала: {e}")
            return False

    # ----- Покупки -----
    def add_purchase(self, user_id, account_number, phone, price):
        try:
            self.cursor.execute('INSERT INTO purchases (user_id, account_number, phone, price) VALUES (?, ?, ?, ?)', (user_id, account_number, phone, price))
            self.conn.commit()
        except Exception as e:
            print(f"Ошибка добавления покупки: {e}")

    def use_discount(self, user_id):
        self.cursor.execute('UPDATE users SET discount_used = 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()

    # ----- Аккаунты -----
    def add_account(self, account_data):
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO accounts
                (account_number, phone, country, country_name, api_id, api_hash, session_file, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (account_data['account_number'], account_data['phone'], account_data['country'],
                  account_data['country_name'], account_data['api_id'], account_data['api_hash'],
                  account_data['session_file'], account_data.get('description', '')))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка добавления аккаунта: {e}")
            return False

    def get_all_accounts(self):
        try:
            self.cursor.execute('SELECT * FROM accounts WHERE is_active = 1 ORDER BY account_id')
            rows = self.cursor.fetchall()
            accounts = {}
            for row in rows:
                accounts[str(row[1])] = {
                    'phone': row[2], 'country': row[3], 'country_name': row[4],
                    'api_id': row[5], 'api_hash': row[6], 'session_file': row[7],
                    'description': row[8], 'in_use': bool(row[9]), 'current_user': row[10],
                    'purchase_date': row[11], 'is_active': bool(row[12])
                }
            return accounts
        except Exception as e:
            print(f"Ошибка получения аккаунтов: {e}")
            return {}

    def get_account(self, account_number):
        try:
            self.cursor.execute('SELECT * FROM accounts WHERE account_number = ? AND is_active = 1', (account_number,))
            row = self.cursor.fetchone()
            if row:
                return {
                    'phone': row[2], 'country': row[3], 'country_name': row[4],
                    'api_id': row[5], 'api_hash': row[6], 'session_file': row[7],
                    'description': row[8], 'in_use': bool(row[9]), 'current_user': row[10],
                    'purchase_date': row[11]
                }
        except Exception as e:
            print(f"Ошибка получения аккаунта: {e}")
        return None

    def update_account_status(self, account_number, user_id, in_use=True):
        try:
            self.cursor.execute('UPDATE accounts SET in_use = ?, current_user = ?, purchase_date = CURRENT_TIMESTAMP WHERE account_number = ?', (1 if in_use else 0, user_id, account_number))
            self.cursor.execute('INSERT INTO account_history (account_id, user_id, action) SELECT account_id, ?, ? FROM accounts WHERE account_number = ?', (user_id, 'purchase' if in_use else 'release', account_number))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка обновления статуса: {e}")
            return False

    def save_session(self, account_number, session_data):
        try:
            self.cursor.execute('INSERT OR REPLACE INTO sessions (account_id, session_data, last_updated) SELECT account_id, ?, CURRENT_TIMESTAMP FROM accounts WHERE account_number = ?', (session_data, account_number))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка сохранения сессии: {e}")
            return False

    def load_sessions_from_db(self):
        try:
            self.cursor.execute('SELECT a.account_number, a.session_file, s.session_data FROM sessions s JOIN accounts a ON s.account_id = a.account_id')
            rows = self.cursor.fetchall()
            restored = 0
            for row in rows:
                account_number, session_file, session_data = row
                try:
                    decoded = base64.b64decode(session_data)
                    with open(f"{session_file}.session", 'wb') as f:
                        f.write(decoded)
                    print(f"✅ Восстановлена сессия для аккаунта {account_number}")
                    restored += 1
                except Exception as e:
                    print(f"❌ Ошибка восстановления сессии {account_number}: {e}")
            return restored
        except Exception as e:
            print(f"Ошибка загрузки сессий: {e}")
            return 0

    def get_account_stats(self):
        try:
            self.cursor.execute('SELECT COUNT(*) as total, SUM(CASE WHEN in_use = 1 THEN 1 ELSE 0 END) as sold, SUM(CASE WHEN in_use = 0 THEN 1 ELSE 0 END) as available FROM accounts WHERE is_active = 1')
            row = self.cursor.fetchone()
            if row:
                return {'total': row[0] or 0, 'sold': row[1] or 0, 'available': row[2] or 0}
        except Exception as e:
            print(f"Ошибка получения статистики аккаунтов: {e}")
        return {'total': 0, 'sold': 0, 'available': 0}

    # ----- Общая статистика приглашений -----
    def get_total_invites_alltime(self):
        try:
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in self.cursor.fetchall()]
            if 'total_invited' in columns:
                self.cursor.execute('SELECT SUM(total_invited) FROM users')
                total = self.cursor.fetchone()[0]
            else:
                self.cursor.execute('SELECT COUNT(*) FROM referrals')
                total = self.cursor.fetchone()[0]
            return total if total else 0
        except Exception as e:
            print(f"Ошибка подсчета всех приглашений: {e}")
            return 0

    # ----- Общая статистика бота -----
    def get_stats(self):
        stats = {}
        try:
            self.cursor.execute("SELECT COUNT(*) FROM users")
            stats['total_users'] = self.cursor.fetchone()[0]
            self.cursor.execute("SELECT COUNT(*) FROM referrals")
            stats['total_refs'] = self.cursor.fetchone()[0]
            self.cursor.execute("SELECT COUNT(*) FROM purchases")
            stats['total_purchases'] = self.cursor.fetchone()[0]
            self.cursor.execute("SELECT SUM(price) FROM purchases")
            total = self.cursor.fetchone()[0]
            stats['total_revenue'] = total if total else 0
        except Exception as e:
            stats = {'total_users': 0, 'total_refs': 0, 'total_purchases': 0, 'total_revenue': 0}
        return stats

    def close(self):
        if self.conn:
            self.conn.close()
            print("✅ База данных закрыта")

db = Database()

# ================== ЗАГРУЗКА АККАУНТОВ ==================
def init_accounts_from_db():
    print("\n🔍 ЗАГРУЗКА АККАУНТОВ ИЗ БД:")
    accounts_from_db = db.get_all_accounts()
    if accounts_from_db:
        print(f"✅ Загружено {len(accounts_from_db)} аккаунтов из БД")
        restored = db.load_sessions_from_db()
        print(f"✅ Восстановлено {restored} сессий из БД")
        return accounts_from_db
    else:
        print("🆕 База данных пуста, создаем начальные аккаунты")
        initial_accounts = {
            "1": { "account_number": "1", "phone": "+16188550568", "country": "us", "country_name": "США", "api_id": API_ID, "api_hash": API_HASH, "session_file": "sessions/account_1", "description": "Аккаунт USA, чистый, прогретый" },
            "2": { "account_number": "2", "phone": "+15593721842", "country": "us", "country_name": "США", "api_id": API_ID, "api_hash": API_HASH, "session_file": "sessions/account_2", "description": "Аккаунт USA, чистый, прогретый" },
            "3": { "account_number": "3", "phone": "+15399999864", "country": "us", "country_name": "США", "api_id": API_ID, "api_hash": API_HASH, "session_file": "sessions/account_3", "description": "Аккаунт USA, чистый, прогретый" }
        }
        for num, acc_data in initial_accounts.items():
            db.add_account(acc_data)
            print(f"✅ Добавлен аккаунт {num} в БД")
        accounts_from_db = db.get_all_accounts()
        for num in initial_accounts:
            session_file = f"sessions/account_{num}.session"
            if os.path.exists(session_file):
                try:
                    with open(session_file, 'rb') as f:
                        session_data = f.read()
                        session_b64 = base64.b64encode(session_data).decode('utf-8')
                        db.save_session(num, session_b64)
                        print(f"✅ Сохранена сессия аккаунта {num} в БД")
                except Exception as e:
                    print(f"❌ Ошибка сохранения сессии {num}: {e}")
        return accounts_from_db

accounts = init_accounts_from_db()
print("=" * 50)

# ================== ПРОВЕРКА БАЗЫ ==================
if os.path.exists("data/bot.db"):
    size = os.path.getsize("data/bot.db")
    print(f"✅ База данных создана: {size} байт")

# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
pending_purchases = {}

def get_user(user_id):
    user = db.get_user(user_id)
    if not user:
        db.add_user(user_id)
        user = db.get_user(user_id)
    return user

def calculate_stars_price(user_id):
    user = get_user(user_id)
    if user["discount"] > 0 and not user.get("discount_used", False):
        return PRICE_STARS - DISCOUNT_STARS
    return PRICE_STARS

# ================== ПРОВЕРКА ПОДПИСКИ ==================
async def check_subscriptions(user_id):
    """Проверяет, подписан ли пользователь на все обязательные каналы"""
    if user_id == ADMIN_ID:
        return True
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel["username"], user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except Exception as e:
            print(f"Ошибка проверки подписки для канала {channel['username']}: {e}")
            return False
    return True

def get_subscription_keyboard():
    """Клавиатура для проверки подписки (с красивым текстом)"""
    kb = InlineKeyboardMarkup(row_width=1)
    for channel in REQUIRED_CHANNELS:
        kb.add(InlineKeyboardButton(
            f"📢 {channel['name']}", 
            url=channel['url']
        ))
    kb.add(InlineKeyboardButton(
        f"{EMOJI['check']} Я ПОДПИСАЛСЯ, ПРОВЕРИТЬ", 
        callback_data="check_subs"
    ))
    return kb

# ================== ДЕКОРАТОР ПРОВЕРКИ ПОДПИСКИ ==================
def subscription_required(handler):
    async def wrapper(message: types.Message):
        user_id = message.from_user.id
        is_subscribed = await check_subscriptions(user_id)
        if not is_subscribed:
            text = (
                f"{EMOJI['guard']} *Доступ к боту ограничен*\n\n"
                f"Для использования бота необходимо подписаться на наш канал:\n\n"
                f"👉 [{REQUIRED_CHANNELS[0]['name']}]({REQUIRED_CHANNELS[0]['url']})\n\n"
                f"Это бесплатно и занимает всего секунду. После подписки нажмите кнопку проверки ниже."
            )
            await message.answer(text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=get_subscription_keyboard())
            return
        return await handler(message)
    return wrapper

# ================== КЛАВИАТУРЫ ==================
def get_main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Номера"), KeyboardButton("💰 Цены"))
    kb.add(KeyboardButton("👥 Мои рефералы"), KeyboardButton("📞 Поддержка"))
    kb.add(KeyboardButton("❓ Помощь"))
    return kb

def get_numbers_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    for num, acc in accounts.items():
        if not acc["in_use"]:
            flag = FLAGS.get(acc["country"], "🌍")
            kb.add(InlineKeyboardButton(
                f"{flag} {acc['phone']} — {acc['description'][:20]}...", 
                callback_data=f"num_{num}"
            ))
    kb.add(InlineKeyboardButton("◀ Назад в меню", callback_data="back"))
    return kb

def get_code_keyboard(number):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(
        f"{EMOJI['code']} Получить код подтверждения", 
        callback_data=f"getcode_{number}"
    ))
    return kb

# ================== КОМАНДЫ ==================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    args = message.get_args()
    
    # Сначала проверяем подписку
    if not await check_subscriptions(user_id):
        text = (
            f"{EMOJI['guard']} *Добро пожаловать!*\n\n"
            f"Для начала работы необходимо подписаться на наш канал:\n\n"
            f"👉 [{REQUIRED_CHANNELS[0]['name']}]({REQUIRED_CHANNELS[0]['url']})\n\n"
            f"После подписки нажмите кнопку ниже."
        )
        await message.answer(text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=get_subscription_keyboard())
        return
    
    user = get_user(user_id)
    db.cursor.execute("SELECT referrer_id FROM referrals WHERE referred_id = ?", (user_id,))
    is_already_referred = db.cursor.fetchone()
    
    if args and not is_already_referred:
        db.cursor.execute("SELECT user_id FROM users WHERE ref_code = ?", (args,))
        result = db.cursor.fetchone()
        if result and result[0] != user_id:
            referrer_id = result[0]
            # Проверяем, подписан ли реферер на канал
            if await check_subscriptions(referrer_id):
                if db.add_referral(referrer_id, user_id):
                    await message.answer(f"{EMOJI['success']} Вы перешли по реферальной ссылке!")
            else:
                await message.answer(f"{EMOJI['warning']} Пригласивший вас пользователь не подписан на канал. Реферал не засчитан.")
        elif result and result[0] == user_id:
            await message.answer(f"{EMOJI['warning']} Нельзя стать рефералом по своей ссылке!")
    elif args and is_already_referred:
        await message.answer(f"{EMOJI['info']} Вы уже чей-то реферал")
    
    text = (
        f"{EMOJI['phone']} *Добро пожаловать в GeoNomer!*\n\n"
        f"{EMOJI['star']} *Цена номера:* {PRICE_STARS} звёзд\n"
        f"{EMOJI['referral']} *Рефералы:* 5 друзей = скидка {DISCOUNT_STARS}⭐\n\n"
        f"👇 Используйте кнопки меню для навигации"
    )
    await message.reply(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# ================== ОБРАБОТЧИК ПРОВЕРКИ ПОДПИСКИ ==================
@dp.callback_query_handler(lambda c: c.data == "check_subs")
async def check_subs_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    is_subscribed = await check_subscriptions(user_id)
    if is_subscribed:
        await call.message.delete()
        await start(call.message)
        await call.answer("✅ Подписка подтверждена! Добро пожаловать.")
    else:
        await call.answer("❌ Вы еще не подписались! Подпишитесь и нажмите снова.", show_alert=True)

# ================== ОСНОВНЫЕ ОБРАБОТЧИКИ ==================
@dp.message_handler(lambda msg: msg.text == "👥 Мои рефералы")
@subscription_required
async def referrals(msg: types.Message):
    user = get_user(msg.from_user.id)
    bot_name = (await bot.get_me()).username
    link = f"https://t.me/{bot_name}?start={user['ref_code']}"
    
    progress_to_discount = "🟩" * min(user['ref_count'], 5) + "⬜" * (5 - min(user['ref_count'], 5))
    
    if user["discount"] > 0 and not user["discount_used"]:
        discount_status = f"{EMOJI['success']} *Доступна*"
        discount_text = f"💰 У вас есть скидка {DISCOUNT_STARS}⭐ на следующий заказ!"
    elif user["discount_used"]:
        discount_status = f"{EMOJI['lock']} *Использована*"
        discount_text = "✅ Скидка уже была применена к заказу"
    else:
        discount_status = f"{EMOJI['wait']} *Недоступна*"
        discount_text = f"👥 Пригласите ещё {5 - user['ref_count']} друзей для получения скидки"
    
    text = (
        f"🎁 *МОЯ РЕФЕРАЛЬНАЯ ПРОГРАММА*\n\n"
        f"{EMOJI['link']} *Твоя ссылка для приглашения:*\n"
        f"`{link}`\n\n"
        f"{EMOJI['stats']} *Твоя статистика:*\n"
        f"• {EMOJI['total']} *Всего приглашено:* `{user['total_invited']}` чел.\n"
        f"• {EMOJI['referral']} *Активно для скидки:* `{user['ref_count']}` чел.\n\n"
        f"{EMOJI['chart']} *Прогресс до скидки (5 чел.):*\n"
        f"{progress_to_discount}\n\n"
        f"🏷️ *Статус скидки:* {discount_status}\n"
        f"ℹ️ {discount_text}\n\n"
        f"📌 *Как это работает:*\n"
        f"1️⃣ Отправьте ссылку друзьям\n"
        f"2️⃣ Когда 5 друзей перейдут по ней\n"
        f"3️⃣ Получите скидку {DISCOUNT_STARS}⭐ на следующий заказ!"
    )
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(f"{EMOJI['link']} Поделиться ссылкой", url=f"https://t.me/share/url?url={link}"))
    await msg.answer(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.message_handler(lambda msg: msg.text == "💰 Цены")
@subscription_required
async def prices(msg: types.Message):
    price = calculate_stars_price(msg.from_user.id)
    text = f"{EMOJI['money']} *Доступные номера:*\n\n"
    for num, acc in accounts.items():
        flag = FLAGS.get(acc["country"], "🌍")
        status = f"{EMOJI['unlock']}" if not acc["in_use"] else f"{EMOJI['lock']}"
        text += f"{flag} `{acc['phone']}` {status}\n"
        text += f"{EMOJI['info']} *{acc['description']}*\n\n"
    text += f"\n{EMOJI['star']} *Твоя цена:* {price} звёзд"
    await msg.answer(text, parse_mode="Markdown")

@dp.message_handler(lambda msg: msg.text == "📱 Номера")
@subscription_required
async def numbers(msg: types.Message):
    await msg.answer("📱 Доступные номера:", reply_markup=get_numbers_keyboard())

@dp.message_handler(lambda msg: msg.text == "📞 Поддержка")
@subscription_required
async def support(msg: types.Message):
    await msg.answer("📞 Связь с поддержкой: @dan4ezHelp")

@dp.message_handler(lambda msg: msg.text == "❓ Помощь")
@subscription_required
async def help_cmd(msg: types.Message):
    help_text = (
        f"{EMOJI['help']} *Помощь по использованию*\n\n"
        f"1️⃣ {EMOJI['phone']} Нажми **'Номера'**\n"
        f"2️⃣ Выбери понравившийся номер\n"
        f"3️⃣ {EMOJI['star']} Оплати звездами\n"
        f"4️⃣ {EMOJI['code']} Нажми **'Получить код'**\n"
        f"5️⃣ ✅ Войди в аккаунт с полученным кодом\n\n"
        f"{EMOJI['referral']} Приглашай друзей и получай скидки!"
    )
    await msg.answer(help_text, parse_mode="Markdown")

# ================== АДМИН КОМАНДЫ ==================
@dp.message_handler(commands=['addaccount'])
async def add_account_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    args = message.get_args().split()
    if len(args) < 3:
        await message.answer(f"{EMOJI['error']} Использование: /addaccount номер телефон страна [описание]")
        return
    account_number = args[0]
    phone = args[1]
    country_name = args[2]
    description = ' '.join(args[3:]) if len(args) > 3 else "Новый аккаунт"
    country_code = "us"
    if "сша" in country_name.lower(): country_code = "us"
    elif "великобрит" in country_name.lower() or "англ" in country_name.lower(): country_code = "gb"
    elif "рос" in country_name.lower() or "ру" in country_name.lower(): country_code = "ru"
    account_data = {
        "account_number": account_number, "phone": phone, "country": country_code,
        "country_name": country_name, "api_id": API_ID, "api_hash": API_HASH,
        "session_file": f"sessions/account_{account_number}", "description": description
    }
    if db.add_account(account_data):
        global accounts
        accounts = db.get_all_accounts()
        await message.answer(f"{EMOJI['success']} Аккаунт {account_number} добавлен в БД")
    else:
        await message.answer(f"{EMOJI['error']} Ошибка добавления аккаунта")

@dp.message_handler(commands=['save_sessions'])
async def save_sessions_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🔄 Сохраняю сессии в БД...")
    saved = 0
    for num in accounts:
        session_file = f"sessions/account_{num}.session"
        if os.path.exists(session_file):
            try:
                with open(session_file, 'rb') as f:
                    session_data = f.read()
                    session_b64 = base64.b64encode(session_data).decode('utf-8')
                    if db.save_session(num, session_b64):
                        saved += 1
            except Exception as e:
                print(f"❌ Ошибка сохранения сессии {num}: {e}")
    await message.answer(f"✅ Сохранено {saved} сессий в БД")

@dp.message_handler(commands=['exportdb'])
async def export_db(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🔄 Экспортирую базу данных...")
    try:
        for num in accounts:
            session_file = f"sessions/account_{num}.session"
            if os.path.exists(session_file):
                with open(session_file, 'rb') as f:
                    session_data = f.read()
                    session_b64 = base64.b64encode(session_data).decode('utf-8')
                    db.save_session(num, session_b64)
        if os.path.exists("data/bot.db"):
            with open("data/bot.db", "rb") as f:
                db_data = f.read()
                db_b64 = base64.b64encode(db_data).decode('utf-8')
                backup_sql = []
                for line in db.conn.iterdump():
                    backup_sql.append(line)
                await message.answer(f"✅ База экспортирована! (Данные в логах Render)")
                print("\n" + "="*50)
                print("DB_BACKUP = ")
                print(db_b64)
                print("\n" + "="*50)
                print("SQL_BACKUP = ")
                print('\n'.join(backup_sql))
                print("="*50 + "\n")
        else:
            await message.answer("❌ База данных не найдена")
    except Exception as e:
        await message.answer(f"❌ Ошибка экспорта: {e}")

@dp.message_handler(commands=['total_invites'])
async def total_invites(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    total = db.get_total_invites_alltime()
    db.cursor.execute('SELECT COUNT(*) FROM referrals')
    referrals_count = db.cursor.fetchone()[0]
    await message.answer(
        f"📊 *ОБЩАЯ СТАТИСТИКА ПРИГЛАШЕНИЙ*\n\n"
        f"👥 *Всего приглашено:* `{total}` человек\n"
        f"📝 *Записей в таблице referrals:* `{referrals_count}`",
        parse_mode="Markdown"
    )

# ================== ВЫБОР НОМЕРА ==================
@dp.callback_query_handler(lambda c: c.data.startswith("num_"))
async def process_number(call: types.CallbackQuery):
    user_id = call.from_user.id
    if not await check_subscriptions(user_id):
        await call.message.answer(
            f"{EMOJI['guard']} *Необходимо подписаться на канал*",
            parse_mode="Markdown",
            reply_markup=get_subscription_keyboard()
        )
        await call.answer()
        return
    number = call.data.replace("num_", "")
    account = db.get_account(number)
    if not account:
        await call.message.answer(f"{EMOJI['error']} Аккаунт не найден")
        await call.answer()
        return
    accounts[number] = account
    if account["in_use"]:
        await call.message.answer(f"{EMOJI['error']} Этот номер уже куплен")
        await call.answer()
        return
    user = get_user(user_id)
    price = calculate_stars_price(user_id)
    pending_purchases[user_id] = { "number": number, "price": price, "use_discount": price < PRICE_STARS }
    flag = FLAGS.get(account["country"], "🌍")
    selection_text = (
        f"{flag} *{account['country_name']}*\n"
        f"📞 `{account['phone']}`\n\n"
        f"{EMOJI['info']} *ОПИСАНИЕ:*\n{account['description']}\n\n"
        f"{EMOJI['star']} *ЦЕНА:* {price} звёзд\n\n"
        f"{EMOJI['payment']} *Нажми кнопку ниже для оплаты*"
    )
    if user_id == ADMIN_ID:
        db.update_account_status(number, user_id, in_use=True)
        accounts[number]["in_use"] = True
        accounts[number]["current_user"] = user_id
        admin_text = (
            f"{EMOJI['crown']} *ТЕСТОВЫЙ РЕЖИМ АДМИНА*\n\n"
            f"{flag} `{account['phone']}`\n\n"
            f"{EMOJI['info']} *Описание:* {account['description']}\n\n"
            f"{EMOJI['key']} *ИНСТРУКЦИЯ ПО ВХОДУ:*\n"
            f"1️⃣ Включи ВПН страны аккаунта ({account['country_name']})\n"
            f"2️⃣ Введи номер в Telegram\n"
            f"3️⃣ Нажми кнопку 'Получить код' ниже\n\n"
            f"{EMOJI['guard']} *ЧТОБЫ АККАУНТ НЕ ЗАБЛОКИРОВАЛИ:*\n"
            f"• {EMOJI['wait2']} Первые 3-7 дней не меняй данные\n"
            f"• {EMOJI['vpn']} Всегда заходи через ВПН страны\n"
            f"• {EMOJI['check']} Дай аккаунту 'отлежаться'\n\n"
            f"{EMOJI['code']} *Нажми кнопку, чтобы получить код:*"
        )
        await call.message.answer(admin_text, parse_mode="Markdown", reply_markup=get_code_keyboard(number))
        await call.answer("✅ Бесплатный тест-режим активирован")
        return
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(f"{EMOJI['payment']} Оплатить {price}⭐", callback_data=f"pay_{number}"))
    keyboard.add(InlineKeyboardButton("◀ Назад", callback_data="back"))
    await call.message.answer(selection_text, parse_mode="Markdown", reply_markup=keyboard)
    await call.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("pay_"))
async def pay_callback(call: types.CallbackQuery):
    number = call.data.replace("pay_", "")
    if number not in accounts:
        await call.answer(f"{EMOJI['error']} Ошибка")
        return
    account = accounts[number]
    flag = FLAGS.get(account["country"], "🌍")
    user_id = call.from_user.id
    purchase = pending_purchases.get(user_id, {})
    price = purchase.get("price", PRICE_STARS)
    prices = [LabeledPrice(label=f"Номер {number}", amount=price)]
    await bot.send_invoice(chat_id=user_id, title=f"Оплата номера {flag}", description=f"{account['phone']}", payload=f"purchase_{number}", provider_token="", currency="XTR", prices=prices)
    await call.answer("💳 Счёт отправлен! Оплати через Telegram")

@dp.callback_query_handler(lambda c: c.data == "back")
async def back(call: types.CallbackQuery):
    await call.message.delete()
    await call.message.answer("👋 Главное меню:", reply_markup=get_main_keyboard())
    await call.answer()

# ================== ПЛАТЕЖИ ==================
@dp.pre_checkout_query_handler(lambda query: True)
async def pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

@dp.message_handler(content_types=['successful_payment'])
async def successful_payment(message: types.Message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        await message.answer(f"{EMOJI['warning']} Вы админ, используйте бесплатный тест-режим")
        return
    user = get_user(user_id)
    purchase = pending_purchases.get(user_id, {})
    number = purchase.get("number", "1")
    account = db.get_account(number)
    if not account:
        await message.answer(f"{EMOJI['error']} Аккаунт не найден")
        return
    if account["in_use"]:
        await message.answer(f"{EMOJI['error']} Аккаунт уже используется")
        return
    db.update_account_status(number, user_id, in_use=True)
    accounts[number]["in_use"] = True
    accounts[number]["current_user"] = user_id
    if purchase.get("use_discount", False):
        db.use_discount(user_id)
    db.add_purchase(user_id, number, account['phone'], message.successful_payment.total_amount)
    flag = FLAGS.get(account["country"], "🌍")
    country_name = account.get("country_name", "этой страны")
    instruction = (
        f"{EMOJI['success']} *ОПЛАЧЕНО!*\n\n"
        f"{flag} `{account['phone']}`\n\n"
        f"{EMOJI['key']} *ИНСТРУКЦИЯ ПО ВХОДУ:*\n"
        f"1️⃣ {EMOJI['vpn']} *ВКЛЮЧИ ВПН СТРАНЫ* ({country_name})\n"
        f"2️⃣ Открой Telegram и введи номер выше\n"
        f"3️⃣ Нажми *'Получить код'*\n"
        f"4️⃣ Нажми кнопку ниже 👇\n\n"
        f"{EMOJI['guard']} *⚠️ ВАЖНО! ЧТОБЫ АККАУНТ НЕ ЗАБЛОКИРОВАЛИ:*\n\n"
        f"🟢 *Первые 3-7 дней (режим 'отлежки'):*\n"
        f"• {EMOJI['vpn']} Заходи ТОЛЬКО через ВПН страны аккаунта\n"
        f"• {EMOJI['lock']} НЕ меняй номер телефона\n"
        f"• {EMOJI['lock']} НЕ меняй пароль\n"
        f"• {EMOJI['lock']} НЕ включай двухфакторку\n"
        f"• {EMOJI['check']} Просто сиди в аккаунте, читай чаты\n\n"
        f"🔵 *Через неделю можно:*\n"
        f"• Сменить пароль\n"
        f"• Добавить свой номер\n"
        f"• Включить 2FA\n"
        f"• Заходить без ВПН\n\n"
        f"{EMOJI['support']} *Вопросы:* @dan4ezHelp\n\n"
        f"{EMOJI['code']} *Нажми кнопку, чтобы получить код:*"
    )
    await message.answer(instruction, parse_mode="Markdown", reply_markup=get_code_keyboard(number))
    await bot.send_message(ADMIN_ID, f"{EMOJI['money']} Продажа!\n👤 ID: {user_id}\n📱 Номер {number}\n⭐ {message.successful_payment.total_amount}")

# ================== ПОЛУЧЕНИЕ КОДА ==================
@dp.callback_query_handler(lambda c: c.data.startswith("getcode_"))
async def get_code_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    number = call.data.replace("getcode_", "")
    if number not in accounts:
        await call.message.answer(f"{EMOJI['error']} Аккаунт не найден")
        await call.answer()
        return
    account = accounts[number]
    if account["current_user"] != user_id:
        await call.message.answer(f"{EMOJI['error']} Это не ваш аккаунт")
        await call.answer()
        return
    await call.message.answer(f"{EMOJI['wait']} *Ищу код для {account['phone']}...*", parse_mode="Markdown")
    code_getter = CodeGetter(account['session_file'])
    code = await code_getter.get_code(account['phone'], account['api_id'], account['api_hash'])
    if code:
        await call.message.answer(f"{EMOJI['code']} *Код подтверждения:*\n\n`{code}`\n\n{EMOJI['time']} *Действителен 5 минут*\n\n{EMOJI['key']} Введи этот код в Telegram для входа", parse_mode="Markdown")
    else:
        await call.message.answer(f"{EMOJI['error']} *Код не найден*\n\n📞 Напиши @dan4ezHelp", parse_mode="Markdown")
    await call.answer()

# ================== ТЕСТ ==================
@dp.message_handler(commands=['test'])
async def test(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🧪 *Начинаю проверку всех аккаунтов...*", parse_mode="Markdown")
    results = []
    for num, acc in accounts.items():
        status = "🟢 СВОБОДЕН" if not acc["in_use"] else "🔴 ПРОДАН"
        await message.answer(f"📱 *Номер {num}*: {acc['phone']}\nСтатус: {status}", parse_mode="Markdown")
        if not acc["in_use"]:
            await message.answer(f"🔄 Проверяю номер {num}...")
            getter = CodeGetter(acc['session_file'])
            code = await getter.get_code(acc['phone'], acc['api_id'], acc['api_hash'])
            if code:
                await message.answer(f"✅ *Номер {num}*: Код получен - `{code}`", parse_mode="Markdown")
                results.append(f"✅ Номер {num}: код получен")
            else:
                await message.answer(f"❌ *Номер {num}*: Код не найден", parse_mode="Markdown")
                results.append(f"❌ Номер {num}: код не найден")
    if results:
        report = "📊 *ИТОГИ ТЕСТА:*\n\n" + "\n".join(results)
        await message.answer(report, parse_mode="Markdown")

# ================== СТАТИСТИКА ==================
@dp.message_handler(commands=['stats'])
async def stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    stats = db.get_stats()
    account_stats = db.get_account_stats()
    total_invites = db.get_total_invites_alltime()
    await message.answer(
        f"{EMOJI['chart']} *СТАТИСТИКА*\n\n"
        f"📱 *АККАУНТЫ:*\n"
        f"{EMOJI['unlock']} Доступно: {account_stats['available']}\n"
        f"{EMOJI['lock']} Продано: {account_stats['sold']}\n"
        f"📊 Всего: {account_stats['total']}\n\n"
        f"👥 *ПОЛЬЗОВАТЕЛИ:*\n"
        f"👤 Всего: {stats['total_users']}\n"
        f"👥 Рефералов (текущих): {stats['total_refs']}\n"
        f"📊 Всего приглашений за всё время: {total_invites}\n\n"
        f"💰 *ПРОДАЖИ:*\n"
        f"🛒 Всего: {stats['total_purchases']}\n"
        f"💎 Звезд: {stats['total_revenue']}⭐",
        parse_mode="Markdown"
    )

# ================== РЕЗЕРВНОЕ КОПИРОВАНИЕ ==================
def backup_database():
    try:
        if os.path.exists("data/bot.db"):
            shutil.copy2("data/bot.db", "data/bot.db.backup")
            print("✅ Создана резервная копия базы данных")
            for num in accounts:
                session_file = f"sessions/account_{num}.session"
                if os.path.exists(session_file):
                    with open(session_file, 'rb') as f:
                        session_data = f.read()
                        session_b64 = base64.b64encode(session_data).decode('utf-8')
                        db.save_session(num, session_b64)
            print("✅ Сессии сохранены в БД")
    except Exception as e:
        print(f"❌ Ошибка создания резервной копии: {e}")

atexit.register(backup_database)
atexit.register(db.close)

# ================== ЗАПУСК ==================
if __name__ == '__main__':
    print("=" * 50)
    print("✅ БОТ ЗАПУЩЕН!")
    print("=" * 50)
    print(f"💰 Цена: {PRICE_STARS}⭐")
    print(f"📱 Аккаунтов: {len(accounts)}")
    print("🧪 Тест: /test")
    print("📊 Экспорт базы: /exportdb")
    print("➕ Добавить аккаунт: /addaccount")
    print("💾 Сохранить сессии: /save_sessions")
    print("📈 Всего приглашений: /total_invites")
    print("👑 Режим админа: БЕСПЛАТНО")
    print("=" * 50)
    time.sleep(2)
    while True:
        try:
            executor.start_polling(dp, skip_updates=True, timeout=20, relax=0.5)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print("🔄 Перезапуск через 5 секунд...")
            time.sleep(5)
            continue
        break
