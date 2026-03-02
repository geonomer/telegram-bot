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
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import LabeledPrice, PreCheckoutQuery, SuccessfulPayment
from pyrogram import Client
from pyrogram.errors import PhoneNumberInvalid, AuthKeyUnregistered, FloodWait
from pyrogram.enums import ChatType

# ================== ПРОВЕРКА И ВОССТАНОВЛЕНИЕ БАЗЫ ==================
def fix_corrupted_db():
    """Проверяет и исправляет поврежденную базу данных"""
    print("\n🔧 ПРОВЕРКА ЦЕЛОСТНОСТИ БАЗЫ ДАННЫХ:")
    
    # Создаем папки
    os.makedirs("sessions", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    
    db_path = "data/bot.db"
    
    # Принудительный сброс базы если есть переменная окружения
    if os.environ.get('RESET_DB') == 'true':
        print("🗑️ Принудительное удаление базы по RESET_DB")
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists("data/bot.db.backup"):
            os.remove("data/bot.db.backup")
    
    # Проверяем существует ли файл
    if os.path.exists(db_path):
        size = os.path.getsize(db_path)
        print(f"📊 Размер файла БД: {size} байт")
        
        # Пробуем подключиться для проверки
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
        
        # Если база повреждена, пытаемся восстановить из бэкапа
        backup_path = "data/bot.db.backup"
        if os.path.exists(backup_path):
            print("🔄 Найден бэкап, восстанавливаем...")
            try:
                # Проверяем бэкап
                test_conn = sqlite3.connect(backup_path)
                test_cursor = test_conn.cursor()
                test_cursor.execute("PRAGMA integrity_check")
                result = test_cursor.fetchone()
                test_conn.close()
                
                if result and result[0] == "ok":
                    shutil.copy2(backup_path, db_path)
                    print("✅ База восстановлена из бэкапа")
                    return True
                else:
                    print("❌ Бэкап тоже поврежден")
            except Exception as e:
                print(f"❌ Ошибка при восстановлении из бэкапа: {e}")
        
        # Если бэкапа нет или он поврежден, создаем новую базу
        print("🆕 Создаем новую базу данных...")
        try:
            # Переименовываем старую для анализа
            if os.path.exists(db_path):
                corrupted_path = f"data/bot.db.corrupted_{int(time.time())}"
                os.rename(db_path, corrupted_path)
                print(f"📦 Поврежденная база сохранена как {corrupted_path}")
            
            # Создаем новую базу
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

# Вызываем проверку перед всем остальным
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
            
            # Создаем резервную копию текущей БД если есть
            if os.path.exists("data/bot.db"):
                # Проверяем текущую БД
                try:
                    test_conn = sqlite3.connect("data/bot.db")
                    test_conn.close()
                    # Если все ок, делаем бэкап
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

# Пытаемся восстановить БД
restore_db_from_env()

# ================== ФУНКЦИИ ВОССТАНОВЛЕНИЯ СЕССИЙ ==================
def restore_sessions():
    """Восстанавливает файлы сессий из переменных окружения"""
    print("\n🔍 ПРОВЕРКА СЕССИЙ В ENV:")
    os.makedirs("sessions", exist_ok=True)
    restored = 0
    
    for i in range(1, 10):  # Проверяем до 10 сессий
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
    """Проверяет наличие и валидность файлов сессий"""
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
    """Пингует самого себя каждые 10 минут"""
    def ping():
        url = os.environ.get('RENDER_EXTERNAL_URL', 'https://telegram-bot.onrender.com')
        while True:
            try:
                response = requests.get(f"{url}/health", timeout=5)
                print(f"✅ Self-ping successful at {time.strftime('%H:%M:%S')} - {response.status_code}")
            except Exception as e:
                print(f"❌ Self-ping failed: {e}")
            time.sleep(600)
    
    thread = threading.Thread(target=ping, daemon=True)
    thread.start()
    print("✅ Self-ping thread started")

self_ping()

# ================== НАСТРОЙКИ ==================
TOKEN = os.environ.get('TOKEN', "8054814092:AAEVkB2fThqWSL_fwoNFZ7oQ7Dtjwr4wNt0")
ADMIN_ID = int(os.environ.get('ADMIN_ID', 5019414179))
API_ID = int(os.environ.get('API_ID', 37379476))
API_HASH = os.environ.get('API_HASH', "67cf40314dc0f31534b4b7feeae39242")

PRICE_STARS = 149
DISCOUNT_STARS = 50

# ================== НАСТРОЙКИ КАНАЛА ==================
CHANNEL_USERNAME = "@Geo_Nomer_Store"  # Юзернейм канала
CHANNEL_URL = "https://t.me/Geo_Nomer_Store"  # Ссылка на канал

FLAGS = {
    "us": "🇺🇸", 
    "ru": "🇷🇺", 
    "gb": "🇬🇧",
    "mm": "🇲🇲"
}

EMOJI = {
    "success": "✅", "error": "❌", "wait": "⏳", "money": "💰",
    "star": "⭐", "phone": "📱", "referral": "👥", "support": "📞",
    "help": "❓", "back": "◀️", "code": "🔐", "warning": "⚠️",
    "crown": "👑", "chart": "📊", "time": "⏱️", "lock": "🔒",
    "unlock": "🔓", "discount": "🏷️", "payment": "💳", "link": "🔗",
    "info": "ℹ️", "star2": "✨", "copy": "📋", "arrow": "👉",
    "key": "🔑", "guard": "🛡️", "settings": "⚙️", "check": "✔️",
    "vpn": "🌐", "wait2": "⏰", "alert": "⚠️", "stats": "📊"
}

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ================== БАЗА ДАННЫХ SQLITE ==================
class Database:
    def __init__(self):
        self.db_path = "data/bot.db"
        self.conn = None
        self.cursor = None
        self.max_retries = 3
        self.connect_with_retry()
        self.create_tables()
        # Добавляем поле total_invited если его нет
        self.migrate_database()
        print("✅ База данных SQLite инициализирована")
    
    def connect_with_retry(self):
        """Подключается к базе с повторными попытками"""
        for attempt in range(self.max_retries):
            try:
                self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=20)
                self.conn.row_factory = sqlite3.Row
                self.cursor = self.conn.cursor()
                
                # Проверяем целостность
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
                    # Пробуем восстановить
                    self.recover_database()
                    time.sleep(2)
                else:
                    # Создаем новую базу
                    self.create_new_database()
        
        return False
    
    def recover_database(self):
        """Пытается восстановить поврежденную базу"""
        print("🔄 Попытка восстановления базы данных...")
        
        backup_path = "data/bot.db.backup"
        
        # Если есть бэкап, пробуем его
        if os.path.exists(backup_path):
            try:
                # Проверяем бэкап
                test_conn = sqlite3.connect(backup_path)
                test_conn.close()
                shutil.copy2(backup_path, self.db_path)
                print("✅ База восстановлена из бэкапа")
                return True
            except:
                pass
        
        # Пробуем восстановить через SQL дамп
        try:
            # Читаем поврежденную базу
            corrupted_conn = sqlite3.connect(self.db_path)
            corrupted_conn.text_factory = bytes  # Читаем как байты для обхода ошибок
            
            # Создаем дамп
            with open('data/dump.sql', 'w') as f:
                for line in corrupted_conn.iterdump():
                    try:
                        # Пытаемся декодировать строку
                        if isinstance(line, bytes):
                            line = line.decode('utf-8', errors='ignore')
                        f.write('%s\n' % line)
                    except:
                        continue
            
            corrupted_conn.close()
            
            # Создаем новую базу из дампа
            os.rename(self.db_path, self.db_path + ".old")
            new_conn = sqlite3.connect(self.db_path)
            with open('data/dump.sql', 'r') as f:
                sql_script = f.read()
                new_conn.executescript(sql_script)
            new_conn.close()
            
            print("✅ База восстановлена через SQL дамп")
            return True
        except Exception as e:
            print(f"❌ Ошибка восстановления: {e}")
            return False
    
    def create_new_database(self):
        """Создает новую базу данных"""
        print("🆕 Создание новой базы данных...")
        
        # Сохраняем старую базу для анализа
        if os.path.exists(self.db_path):
            corrupted_path = f"data/bot.db.corrupted_{int(time.time())}"
            os.rename(self.db_path, corrupted_path)
            print(f"📦 Поврежденная база сохранена как {corrupted_path}")
        
        # Создаем новую
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=20)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        print("✅ Новая база данных создана")
    
    def migrate_database(self):
        """Добавляет поле total_invited в существующую таблицу"""
        try:
            # Проверяем, есть ли поле total_invited
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in self.cursor.fetchall()]
            
            if 'total_invited' not in columns:
                print("🔄 Добавляем поле total_invited в таблицу users...")
                self.cursor.execute('ALTER TABLE users ADD COLUMN total_invited INTEGER DEFAULT 0')
                self.conn.commit()
                print("✅ Поле total_invited добавлено")
                
                # Обновляем существующие записи: total_invited = ref_count
                self.cursor.execute('UPDATE users SET total_invited = ref_count')
                self.conn.commit()
                print(f"✅ Обновлено {self.cursor.rowcount} записей")
        except Exception as e:
            print(f"⚠️ Ошибка при миграции: {e}")
    
    def create_tables(self):
        """Создает таблицы, если их нет"""
        # Таблица пользователей
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
        
        # Таблица рефералов
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
        
        # Таблица для отслеживания переходов по ссылкам (новая)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ref_code TEXT NOT NULL,
                clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, ref_code)
            )
        ''')
        
        # Таблица покупок
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
        
        # Таблица для аккаунтов
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
        
        # Таблица для истории использования аккаунтов
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
        
        # Таблица для сессий (base64)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                account_id INTEGER PRIMARY KEY,
                session_data TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(account_id)
            )
        ''')
        
        self.conn.commit()
    
    # ========== МЕТОДЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ==========
    def add_user(self, user_id):
        try:
            max_attempts = 10
            for attempt in range(max_attempts):
                ref_code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                self.cursor.execute("SELECT user_id FROM users WHERE ref_code = ?", (ref_code,))
                if not self.cursor.fetchone():
                    break
            else:
                ref_code = f"user_{user_id}"
            
            self.cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, ref_code)
                VALUES (?, ?)
            ''', (user_id, ref_code))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка добавления пользователя {user_id}: {e}")
            return False
    
    def get_user(self, user_id):
        try:
            # Проверяем наличие поля total_invited
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in self.cursor.fetchall()]
            
            if 'total_invited' in columns:
                self.cursor.execute('''
                    SELECT user_id, ref_code, ref_count, discount, discount_used, discount_given, total_invited
                    FROM users WHERE user_id = ?
                ''', (user_id,))
                row = self.cursor.fetchone()
                
                if row:
                    return {
                        "user_id": row[0],
                        "ref_code": row[1],
                        "ref_count": row[2],
                        "discount": row[3],
                        "discount_used": bool(row[4]),
                        "discount_given": bool(row[5]),
                        "total_invited": row[6] or 0
                    }
            else:
                self.cursor.execute('''
                    SELECT user_id, ref_code, ref_count, discount, discount_used, discount_given
                    FROM users WHERE user_id = ?
                ''', (user_id,))
                row = self.cursor.fetchone()
                
                if row:
                    return {
                        "user_id": row[0],
                        "ref_code": row[1],
                        "ref_count": row[2],
                        "discount": row[3],
                        "discount_used": bool(row[4]),
                        "discount_given": bool(row[5]),
                        "total_invited": row[2]  # Используем ref_count как запасной
                    }
        except Exception as e:
            print(f"Ошибка получения пользователя {user_id}: {e}")
        
        return None
    
    # ========== МЕТОДЫ ДЛЯ РЕФЕРАЛОВ ==========
    def can_use_referral(self, user_id, ref_code):
        """Проверяет, может ли пользователь использовать реферальную ссылку"""
        try:
            # Проверяем, не переходил ли уже по этой ссылке
            self.cursor.execute('SELECT id FROM referral_clicks WHERE user_id = ? AND ref_code = ?', (user_id, ref_code))
            if self.cursor.fetchone():
                return False, "Вы уже переходили по этой ссылке"
            
            # Проверяем, не является ли уже чьим-то рефералом
            self.cursor.execute('SELECT id FROM referrals WHERE referred_id = ?', (user_id,))
            if self.cursor.fetchone():
                return False, "Вы уже являетесь чьим-то рефералом"
            
            # Получаем реферера
            self.cursor.execute('SELECT user_id FROM users WHERE ref_code = ?', (ref_code,))
            referrer = self.cursor.fetchone()
            if not referrer:
                return False, "Недействительный реферальный код"
            
            referrer_id = referrer[0]
            
            # Нельзя стать рефералом самого себя
            if referrer_id == user_id:
                return False, "Нельзя стать рефералом по своей ссылке"
            
            return True, referrer_id
        except Exception as e:
            print(f"Ошибка проверки реферала: {e}")
            return False, "Ошибка проверки"
    
    def record_referral_click(self, user_id, ref_code):
        """Записывает факт перехода по ссылке"""
        try:
            self.cursor.execute('INSERT OR IGNORE INTO referral_clicks (user_id, ref_code) VALUES (?, ?)', (user_id, ref_code))
            self.conn.commit()
        except Exception as e:
            print(f"Ошибка записи клика: {e}")
    
    def add_referral(self, referrer_id, referred_id):
        try:
            self.cursor.execute("SELECT id FROM referrals WHERE referred_id = ?", (referred_id,))
            if self.cursor.fetchone():
                return False
            
            if referrer_id == referred_id:
                return False
            
            # Начинаем транзакцию
            self.cursor.execute("BEGIN TRANSACTION")
            
            self.cursor.execute('''
                INSERT INTO referrals (referrer_id, referred_id)
                VALUES (?, ?)
            ''', (referrer_id, referred_id))
            
            # Проверяем наличие поля total_invited
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in self.cursor.fetchall()]
            
            if 'total_invited' in columns:
                self.cursor.execute('''
                    UPDATE users 
                    SET ref_count = ref_count + 1,
                        total_invited = total_invited + 1
                    WHERE user_id = ?
                ''', (referrer_id,))
            else:
                self.cursor.execute('''
                    UPDATE users 
                    SET ref_count = ref_count + 1
                    WHERE user_id = ?
                ''', (referrer_id,))
            
            self.cursor.execute('''
                SELECT ref_count FROM users WHERE user_id = ?
            ''', (referrer_id,))
            ref_count_row = self.cursor.fetchone()
            if ref_count_row:
                ref_count = ref_count_row[0]
                
                if ref_count >= 5:
                    self.cursor.execute('''
                        UPDATE users 
                        SET discount = ?, discount_given = 1 
                        WHERE user_id = ? AND discount_given = 0
                    ''', (DISCOUNT_STARS, referrer_id))
            
            self.conn.commit()
            return True
        except Exception as e:
            self.cursor.execute("ROLLBACK")
            print(f"Ошибка добавления реферала: {e}")
            return False
    
    # ========== МЕТОДЫ ДЛЯ ПОКУПОК ==========
    def add_purchase(self, user_id, account_number, phone, price):
        try:
            self.cursor.execute('''
                INSERT INTO purchases (user_id, account_number, phone, price)
                VALUES (?, ?, ?, ?)
            ''', (user_id, account_number, phone, price))
            self.conn.commit()
        except Exception as e:
            print(f"Ошибка добавления покупки: {e}")
    
    def use_discount(self, user_id):
        self.cursor.execute('''
            UPDATE users SET discount_used = 1 WHERE user_id = ?
        ''', (user_id,))
        self.conn.commit()
    
    # ========== МЕТОДЫ ДЛЯ АККАУНТОВ ==========
    def add_account(self, account_data):
        """Добавляет новый аккаунт в БД"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO accounts 
                (account_number, phone, country, country_name, api_id, api_hash, session_file, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                account_data['account_number'],
                account_data['phone'],
                account_data['country'],
                account_data['country_name'],
                account_data['api_id'],
                account_data['api_hash'],
                account_data['session_file'],
                account_data.get('description', '')
            ))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка добавления аккаунта: {e}")
            return False
    
    def get_all_accounts(self):
        """Получает все аккаунты из БД"""
        try:
            self.cursor.execute('''
                SELECT * FROM accounts WHERE is_active = 1 ORDER BY account_id
            ''')
            rows = self.cursor.fetchall()
            
            accounts = {}
            for row in rows:
                accounts[str(row[1])] = {  # account_number как ключ
                    'phone': row[2],
                    'country': row[3],
                    'country_name': row[4],
                    'api_id': row[5],
                    'api_hash': row[6],
                    'session_file': row[7],
                    'description': row[8],
                    'in_use': bool(row[9]),
                    'current_user': row[10],
                    'purchase_date': row[11],
                    'is_active': bool(row[12])
                }
            return accounts
        except Exception as e:
            print(f"Ошибка получения аккаунтов: {e}")
            return {}
    
    def get_account(self, account_number):
        """Получает аккаунт по номеру"""
        try:
            self.cursor.execute('''
                SELECT * FROM accounts WHERE account_number = ? AND is_active = 1
            ''', (account_number,))
            row = self.cursor.fetchone()
            
            if row:
                return {
                    'phone': row[2],
                    'country': row[3],
                    'country_name': row[4],
                    'api_id': row[5],
                    'api_hash': row[6],
                    'session_file': row[7],
                    'description': row[8],
                    'in_use': bool(row[9]),
                    'current_user': row[10],
                    'purchase_date': row[11]
                }
        except Exception as e:
            print(f"Ошибка получения аккаунта: {e}")
        return None
    
    def update_account_status(self, account_number, user_id, in_use=True):
        """Обновляет статус использования аккаунта"""
        try:
            self.cursor.execute('''
                UPDATE accounts 
                SET in_use = ?, current_user = ?, purchase_date = CURRENT_TIMESTAMP
                WHERE account_number = ?
            ''', (1 if in_use else 0, user_id, account_number))
            
            # Добавляем запись в историю
            self.cursor.execute('''
                INSERT INTO account_history (account_id, user_id, action)
                SELECT account_id, ?, ? FROM accounts WHERE account_number = ?
            ''', (user_id, 'purchase' if in_use else 'release', account_number))
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка обновления статуса: {e}")
            return False
    
    def save_session(self, account_number, session_data):
        """Сохраняет сессию аккаунта в БД"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO sessions (account_id, session_data, last_updated)
                SELECT account_id, ?, CURRENT_TIMESTAMP FROM accounts WHERE account_number = ?
            ''', (session_data, account_number))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка сохранения сессии: {e}")
            return False
    
    def load_sessions_from_db(self):
        """Загружает все сессии из БД и восстанавливает файлы"""
        try:
            self.cursor.execute('''
                SELECT a.account_number, a.session_file, s.session_data 
                FROM sessions s
                JOIN accounts a ON s.account_id = a.account_id
            ''')
            rows = self.cursor.fetchall()
            
            restored = 0
            for row in rows:
                account_number, session_file, session_data = row
                try:
                    # Декодируем и сохраняем файл
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
        """Получает статистику по аккаунтам"""
        try:
            self.cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN in_use = 1 THEN 1 ELSE 0 END) as sold,
                    SUM(CASE WHEN in_use = 0 THEN 1 ELSE 0 END) as available
                FROM accounts WHERE is_active = 1
            ''')
            row = self.cursor.fetchone()
            
            if row:
                return {
                    'total': row[0] or 0,
                    'sold': row[1] or 0,
                    'available': row[2] or 0
                }
        except Exception as e:
            print(f"Ошибка получения статистики аккаунтов: {e}")
        return {'total': 0, 'sold': 0, 'available': 0}
    
    # ========== НОВЫЙ МЕТОД ДЛЯ ПОДСЧЕТА ВСЕХ ПРИГЛАШЕНИЙ ==========
    def get_total_invites_alltime(self):
        """Возвращает общее количество приглашенных людей за всё время"""
        try:
            # Проверяем наличие поля total_invited
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in self.cursor.fetchall()]
            
            if 'total_invited' in columns:
                self.cursor.execute('SELECT SUM(total_invited) FROM users')
                total = self.cursor.fetchone()[0]
            else:
                # Если поля нет - считаем по таблице referrals
                self.cursor.execute('SELECT COUNT(*) FROM referrals')
                total = self.cursor.fetchone()[0]
            
            return total if total else 0
        except Exception as e:
            print(f"Ошибка подсчета всех приглашений: {e}")
            return 0
    
    # ========== СТАТИСТИКА ==========
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

# ================== ЗАГРУЗКА АККАУНТОВ ИЗ БД ==================
def init_accounts_from_db():
    """Инициализирует аккаунты из базы данных"""
    print("\n🔍 ЗАГРУЗКА АККАУНТОВ ИЗ БД:")
    
    # Проверяем, есть ли аккаунты в БД
    accounts_from_db = db.get_all_accounts()
    
    if accounts_from_db:
        print(f"✅ Загружено {len(accounts_from_db)} аккаунтов из БД")
        
        # Загружаем сессии
        restored = db.load_sessions_from_db()
        print(f"✅ Восстановлено {restored} сессий из БД")
        
        return accounts_from_db
    else:
        print("🆕 База данных пуста, создаем начальные аккаунты")
        
        # Начальные данные аккаунтов
        initial_accounts = {
            "1": {
                "account_number": "1",
                "phone": "+16188550568",
                "country": "us",
                "country_name": "США",
                "api_id": API_ID,
                "api_hash": API_HASH,
                "session_file": "sessions/account_1",
                "description": "Аккаунт USA, чистый, прогретый"
            },
            "2": {
                "account_number": "2",
                "phone": "+15593721842",
                "country": "us",
                "country_name": "США",
                "api_id": API_ID,
                "api_hash": API_HASH,
                "session_file": "sessions/account_2",
                "description": "Аккаунт USA, чистый, прогретый"
            },
            "3": {
                "account_number": "3",
                "phone": "+15399999864",
                "country": "us",
                "country_name": "США",
                "api_id": API_ID,
                "api_hash": API_HASH,
                "session_file": "sessions/account_3",
                "description": "Аккаунт USA, чистый, прогретый"
            }
        }
        
        for num, acc_data in initial_accounts.items():
            db.add_account(acc_data)
            print(f"✅ Добавлен аккаунт {num} в БД")
        
        # Загружаем созданные аккаунты
        accounts_from_db = db.get_all_accounts()
        
        # Сохраняем существующие файлы сессий в БД
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

# Загружаем аккаунты
accounts = init_accounts_from_db()
print("=" * 50)

# ================== ПРОВЕРКА БАЗЫ ==================
if os.path.exists("data/bot.db"):
    size = os.path.getsize("data/bot.db")
    print(f"✅ База данных создана: {size} байт")

# ================== ВРЕМЕННЫЕ ДАННЫЕ ==================
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

# ================== ПРОВЕРКА ПОДПИСКИ НА КАНАЛ ==================
async def check_subscription(user_id):
    """Проверяет, подписан ли пользователь на канал"""
    if user_id == ADMIN_ID:
        return True  # Админ может пользоваться без подписки
    
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Ошибка проверки подписки для {user_id}: {e}")
        return False

def get_subscription_keyboard():
    """Клавиатура для проверки подписки"""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(
        f"{EMOJI['guard']} Подписаться на канал", 
        url=CHANNEL_URL
    ))
    kb.add(InlineKeyboardButton(
        f"{EMOJI['check']} Я подписался ✅", 
        callback_data="check_sub"
    ))
    return kb

# ================== КЛАСС ДЛЯ ПОЛУЧЕНИЯ КОДА ==================
class CodeGetter:
    def __init__(self, session_file):
        self.session_file = session_file
        print(f"✅ CodeGetter готов для {session_file}")
    
    async def get_code(self, phone, api_id, api_hash):
        try:
            print(f"🔄 Подключаюсь к {phone}...")
            
            session_path = f"{self.session_file}.session"
            if not os.path.exists(session_path):
                print(f"❌ Файл сессии {session_path} не найден")
                return None
            
            app = Client(
                name=self.session_file,
                api_id=api_id,
                api_hash=api_hash,
                workdir="."
            )
            
            await app.start()
            print(f"✅ Успешно подключился!")
            
            me = await app.get_me()
            print(f"👤 Аккаунт: {me.first_name}")
            
            # Ищем диалог с Telegram
            telegram_chat_id = None
            async for dialog in app.get_dialogs(limit=50):
                chat = dialog.chat
                if chat.first_name and "telegram" in chat.first_name.lower():
                    telegram_chat_id = chat.id
                    print(f"✅ Найден чат Telegram: {chat.first_name}")
                    break
            
            if not telegram_chat_id:
                print("❌ Чат Telegram не найден")
                await app.stop()
                return None
            
            # Читаем последние сообщения
            async for msg in app.get_chat_history(telegram_chat_id, limit=20):
                if msg and msg.text:
                    code_match = re.search(r'(\d{5})', msg.text)
                    if code_match:
                        code = code_match.group(1)
                        print(f"✅ НАЙДЕН КОД: {code}")
                        await app.stop()
                        return code
            
            print("❌ Код не найден")
            await app.stop()
            return None
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return None

# ================== КЛАВИАТУРЫ ==================
def get_main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Номера"), KeyboardButton("💰 Цены"))
    kb.add(KeyboardButton("👥 Рефералы"), KeyboardButton("📞 Поддержка"))
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
    
    # Проверяем подписку на канал
    if not await check_subscription(user_id):
        text = (
            f"{EMOJI['guard']} *Для работы с ботом необходимо подписаться на канал!*\n\n"
            f"📢 *Канал:* {CHANNEL_USERNAME}\n\n"
            f"После подписки нажми кнопку *'Я подписался'*"
        )
        await message.answer(text, parse_mode="Markdown", reply_markup=get_subscription_keyboard())
        return
    
    user = get_user(user_id)
    
    # Обработка реферальной ссылки
    if args:
        can_use, result = db.can_use_referral(user_id, args)
        
        if can_use:
            # Записываем переход
            db.record_referral_click(user_id, args)
            
            # Добавляем реферала
            if db.add_referral(result, user_id):
                await message.answer(f"{EMOJI['success']} Вы перешли по реферальной ссылке!")
            else:
                await message.answer(f"{EMOJI['warning']} Не удалось добавить реферала")
        else:
            await message.answer(f"{EMOJI['info']} {result}")
    
    text = (
        f"{EMOJI['phone']} *Добро пожаловать!*\n\n"
        f"{EMOJI['star']} *Цена:* {PRICE_STARS} звёзд\n"
        f"{EMOJI['referral']} *Рефералы:* 5 друзей = скидка {DISCOUNT_STARS} {EMOJI['star']}"
    )
    await message.reply(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.callback_query_handler(lambda c: c.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    
    # Проверяем подписку
    is_subscribed = await check_subscription(user_id)
    
    if is_subscribed:
        await call.message.delete()
        await start(call.message)
        await call.answer("✅ Подписка подтверждена!")
    else:
        await call.answer("❌ Вы еще не подписались! Подпишитесь и нажмите снова", show_alert=True)

@dp.message_handler(lambda msg: msg.text == "👥 Рефералы")
async def referrals(msg: types.Message):
    user_id = msg.from_user.id
    
    # Проверяем подписку
    if not await check_subscription(user_id):
        text = f"{EMOJI['guard']} *Для просмотра рефералов подпишитесь на канал!*\n\n📢 *Канал:* {CHANNEL_USERNAME}"
        await msg.answer(text, parse_mode="Markdown", reply_markup=get_subscription_keyboard())
        return
    
    user = get_user(user_id)
    bot_name = (await bot.get_me()).username
    link = f"https://t.me/{bot_name}?start={user['ref_code']}"
    
    progress = "🟩" * user['ref_count'] + "⬜" * (5 - user['ref_count'])
    
    # Статус скидки
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
        f"🎁 *РЕФЕРАЛЬНАЯ ПРОГРАММА*\n\n"
        f"{EMOJI['star2']} *Приглашайте друзей и получайте скидки!*\n\n"
        f"{EMOJI['link']} *Твоя ссылка:*\n"
        f"`{link}`\n\n"
        f"{EMOJI['stats']} *Твоя статистика:*\n"
        f"• {EMOJI['referral']} *Приглашено всего:* `{user['total_invited']}` чел.\n"
        f"• {EMOJI['star']} *Активно для скидки:* `{user['ref_count']}/5`\n\n"
        f"{EMOJI['chart']} *Прогресс:*\n"
        f"{progress}\n\n"
        f"🏷️ *Статус скидки:* {discount_status}\n"
        f"ℹ️ {discount_text}\n\n"
        f"📌 *Как это работает:*\n"
        f"1️⃣ Отправьте ссылку друзьям\n"
        f"2️⃣ Когда 5 друзей перейдут по ней\n"
        f"3️⃣ Получите скидку {DISCOUNT_STARS}⭐ на следующий заказ!\n\n"
        f"{EMOJI['support']} *Поддержка:* @dan4ezHelp"
    )
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(
        f"{EMOJI['link']} Открыть реферальную ссылку", 
        url=link
    ))
    
    await msg.answer(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.message_handler(lambda msg: msg.text == "💰 Цены")
async def prices(msg: types.Message):
    user_id = msg.from_user.id
    
    # Проверяем подписку
    if not await check_subscription(user_id):
        text = f"{EMOJI['guard']} *Для просмотра цен подпишитесь на канал!*\n\n📢 *Канал:* {CHANNEL_USERNAME}"
        await msg.answer(text, parse_mode="Markdown", reply_markup=get_subscription_keyboard())
        return
    
    price = calculate_stars_price(user_id)
    
    text = f"{EMOJI['money']} *Доступные номера:*\n\n"
    for num, acc in accounts.items():
        flag = FLAGS.get(acc["country"], "🌍")
        status = f"{EMOJI['unlock']}" if not acc["in_use"] else f"{EMOJI['lock']}"
        text += f"{flag} `{acc['phone']}` {status}\n"
        text += f"{EMOJI['info']} *{acc['description']}*\n\n"
    
    text += f"\n{EMOJI['star']} *Твоя цена:* {price} звёзд"
    await msg.answer(text, parse_mode="Markdown")

@dp.message_handler(lambda msg: msg.text == "📱 Номера")
async def numbers(msg: types.Message):
    user_id = msg.from_user.id
    
    # Проверяем подписку
    if not await check_subscription(user_id):
        text = f"{EMOJI['guard']} *Для просмотра номеров подпишитесь на канал!*\n\n📢 *Канал:* {CHANNEL_USERNAME}"
        await msg.answer(text, parse_mode="Markdown", reply_markup=get_subscription_keyboard())
        return
    
    await msg.answer("📱 Доступные номера:", reply_markup=get_numbers_keyboard())

@dp.message_handler(lambda msg: msg.text == "📞 Поддержка")
async def support(msg: types.Message):
    user_id = msg.from_user.id
    
    # Проверяем подписку
    if not await check_subscription(user_id):
        text = f"{EMOJI['guard']} *Для связи с поддержкой подпишитесь на канал!*\n\n📢 *Канал:* {CHANNEL_USERNAME}"
        await msg.answer(text, parse_mode="Markdown", reply_markup=get_subscription_keyboard())
        return
    
    await msg.answer("📞 @dan4ezHelp")

@dp.message_handler(lambda msg: msg.text == "❓ Помощь")
async def help_cmd(msg: types.Message):
    user_id = msg.from_user.id
    
    # Проверяем подписку
    if not await check_subscription(user_id):
        text = f"{EMOJI['guard']} *Для получения помощи подпишитесь на канал!*\n\n📢 *Канал:* {CHANNEL_USERNAME}"
        await msg.answer(text, parse_mode="Markdown", reply_markup=get_subscription_keyboard())
        return
    
    help_text = (
        f"{EMOJI['help']} *Помощь*\n\n"
        f"1️⃣ {EMOJI['phone']} Нажми *'Номера'*\n"
        f"2️⃣ Выбери номер\n"
        f"3️⃣ {EMOJI['star']} Оплати\n"
        f"4️⃣ {EMOJI['code']} Нажми кнопку *'Получить код'*\n"
        f"5️⃣ ✅ Войди в аккаунт\n\n"
        f"{EMOJI['referral']} 5 друзей = скидка {DISCOUNT_STARS}⭐"
    )
    await msg.answer(help_text, parse_mode="Markdown")

# ================== АДМИН КОМАНДЫ ==================
@dp.message_handler(commands=['addaccount'])
async def add_account_cmd(message: types.Message):
    """Добавляет новый аккаунт в БД (только для админа)"""
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.get_args().split()
    if len(args) < 3:
        await message.answer(
            f"{EMOJI['error']} Использование:\n"
            f"/addaccount номер телефон страна [описание]\n\n"
            f"Пример: /addaccount 4 +1234567890 США Аккаунт USA"
        )
        return
    
    account_number = args[0]
    phone = args[1]
    country_name = args[2]
    description = ' '.join(args[3:]) if len(args) > 3 else "Новый аккаунт"
    
    # Определяем код страны
    country_code = "us"  # По умолчанию
    if "сша" in country_name.lower():
        country_code = "us"
    elif "великобрит" in country_name.lower() or "англ" in country_name.lower():
        country_code = "gb"
    elif "рос" in country_name.lower() or "ру" in country_name.lower():
        country_code = "ru"
    
    account_data = {
        "account_number": account_number,
        "phone": phone,
        "country": country_code,
        "country_name": country_name,
        "api_id": API_ID,
        "api_hash": API_HASH,
        "session_file": f"sessions/account_{account_number}",
        "description": description
    }
    
    if db.add_account(account_data):
        # Обновляем локальный словарь
        global accounts
        accounts = db.get_all_accounts()
        await message.answer(f"{EMOJI['success']} Аккаунт {account_number} добавлен в БД")
    else:
        await message.answer(f"{EMOJI['error']} Ошибка добавления аккаунта")

@dp.message_handler(commands=['save_sessions'])
async def save_sessions_cmd(message: types.Message):
    """Сохраняет все текущие сессии в БД"""
    if message.from_user.id != ADMIN_ID:
        return
    
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
    """Экспортирует всю базу данных"""
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer("🔄 Экспортирую базу данных...")
    
    try:
        # Сохраняем сессии в БД перед экспортом
        for num in accounts:
            session_file = f"sessions/account_{num}.session"
            if os.path.exists(session_file):
                with open(session_file, 'rb') as f:
                    session_data = f.read()
                    session_b64 = base64.b64encode(session_data).decode('utf-8')
                    db.save_session(num, session_b64)
        
        # Экспортируем БД
        if os.path.exists("data/bot.db"):
            with open("data/bot.db", "rb") as f:
                db_data = f.read()
                db_b64 = base64.b64encode(db_data).decode('utf-8')
                
                # Также создаем дамп SQL для бэкапа
                backup_sql = []
                for line in db.conn.iterdump():
                    backup_sql.append(line)
                
                await message.answer(
                    f"✅ База экспортирована!\n\n"
                    f"📊 Размер: {len(db_b64)} символов\n\n"
                    f"📋 Скопируй строки в переменные окружения:\n"
                    f"• DB_BACKUP (base64 всей БД)\n"
                    f"• SQL_BACKUP (SQL дамп)\n\n"
                    f"(полный текст в логах Render)"
                )
                
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

# ================== ВЫБОР НОМЕРА ==================
@dp.callback_query_handler(lambda c: c.data.startswith("num_"))
async def process_number(call: types.CallbackQuery):
    user_id = call.from_user.id
    
    # Проверяем подписку
    if not await check_subscription(user_id):
        await call.message.answer(
            f"{EMOJI['guard']} *Для выбора номера подпишитесь на канал!*",
            parse_mode="Markdown",
            reply_markup=get_subscription_keyboard()
        )
        await call.answer()
        return
    
    number = call.data.replace("num_", "")
    
    # Получаем актуальные данные из БД
    account = db.get_account(number)
    if not account:
        await call.message.answer(f"{EMOJI['error']} Аккаунт не найден")
        await call.answer()
        return
    
    # Обновляем локальный словарь
    accounts[number] = account
    
    if account["in_use"]:
        await call.message.answer(f"{EMOJI['error']} Этот номер уже куплен")
        await call.answer()
        return
    
    user = get_user(user_id)
    price = calculate_stars_price(user_id)
    
    pending_purchases[user_id] = {
        "number": number,
        "price": price,
        "use_discount": price < PRICE_STARS
    }
    
    flag = FLAGS.get(account["country"], "🌍")
    
    selection_text = (
        f"{flag} *{account['country_name']}*\n"
        f"📞 `{account['phone']}`\n\n"
        f"{EMOJI['info']} *ОПИСАНИЕ:*\n{account['description']}\n\n"
        f"{EMOJI['star']} *ЦЕНА:* {price} звёзд\n\n"
        f"{EMOJI['payment']} *Нажми кнопку ниже для оплаты*"
    )
    
    if user_id == ADMIN_ID:
        # Обновляем статус в БД
        db.update_account_status(number, user_id, in_use=True)
        
        # Обновляем локальный словарь
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
        
        await call.message.answer(
            admin_text,
            parse_mode="Markdown",
            reply_markup=get_code_keyboard(number)
        )
        await call.answer("✅ Бесплатный тест-режим активирован")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(
        f"{EMOJI['payment']} Оплатить {price}⭐", 
        callback_data=f"pay_{number}"
    ))
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
    await bot.send_invoice(
        chat_id=user_id,
        title=f"Оплата номера {flag}",
        description=f"{account['phone']}",
        payload=f"purchase_{number}",
        provider_token="",
        currency="XTR",
        prices=prices
    )
    
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
    
    # Получаем аккаунт из БД
    account = db.get_account(number)
    if not account:
        await message.answer(f"{EMOJI['error']} Аккаунт не найден")
        return
    
    if account["in_use"]:
        await message.answer(f"{EMOJI['error']} Аккаунт уже используется")
        return
    
    # Обновляем статус в БД
    db.update_account_status(number, user_id, in_use=True)
    
    # Обновляем локальный словарь
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
    
    await message.answer(
        instruction,
        parse_mode="Markdown",
        reply_markup=get_code_keyboard(number)
    )
    
    await bot.send_message(
        ADMIN_ID,
        f"{EMOJI['money']} Продажа!\n"
        f"👤 ID: {user_id}\n"
        f"📱 Номер {number}\n"
        f"⭐ {message.successful_payment.total_amount}"
    )

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
        await call.message.answer(
            f"{EMOJI['code']} *Код подтверждения:*\n\n"
            f"`{code}`\n\n"
            f"{EMOJI['time']} *Действителен 5 минут*\n\n"
            f"{EMOJI['key']} Введи этот код в Telegram для входа",
            parse_mode="Markdown"
        )
    else:
        await call.message.answer(
            f"{EMOJI['error']} *Код не найден*\n\n"
            f"📞 Напиши @dan4ezHelp",
            parse_mode="Markdown"
        )
    
    await call.answer()

# ================== ТЕСТ ==================
@dp.message_handler(commands=['test'])
async def test(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer("🧪 *Начинаю проверку всех аккаунтов...*", parse_mode="Markdown")
    
    results = []
    for num, acc in accounts.items():
        if not acc["in_use"]:
            status = "🟢 СВОБОДЕН"
        else:
            status = "🔴 ПРОДАН"
        
        await message.answer(f"📱 *Номер {num}*: {acc['phone']}\nСтатус: {status}", parse_mode="Markdown")
        
        if not acc["in_use"]:
            await message.answer(f"🔄 Проверяю номер {num}...")
            getter = CodeGetter(acc['session_file'])
            code = await getter.get_code(
                acc['phone'],
                acc['api_id'],
                acc['api_hash']
            )
            
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
    if message.from_user.id != ADMIN_ID:
        return
    
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
        f"👥 Рефералов: {stats['total_refs']}\n"
        f"📊 Всего приглашений: {total_invites}\n\n"
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
            
            # Также сохраняем сессии в БД
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

# ================== ЗАКРЫТИЕ БАЗЫ ==================
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
    
    executor.start_polling(dp, skip_updates=True)
