# -*- coding: utf-8 -*-
import asyncio
import random
import string
import os
import re
import sqlite3
import atexit
import base64
import os
import requests
import threading
import time

def self_ping():
    """Пингует самого себя каждые 10 минут"""
    url = os.environ.get('RENDER_EXTERNAL_URL', 'https://telegram-bot.onrender.com')
    while True:
        try:
            requests.get(f"{url}/health", timeout=5)
            print(f"✅ Self-ping successful at {time.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"❌ Self-ping failed: {e}")
        time.sleep(600)  # 10 минут

# Запусти это после Flask сервера
threading.Thread(target=self_ping, daemon=True).start()

def restore_sessions():
    """Восстанавливает файлы сессий из переменных окружения"""
    os.makedirs("sessions", exist_ok=True)
    
    for i in range(1, 4):
        session_data = os.environ.get(f'SESSION_{i}')
        if session_data:
            try:
                # Убираем лишние переносы строк из base64
                session_data = session_data.replace('\n', '').replace('\r', '')
                with open(f'sessions/account_{i}.session', 'wb') as f:
                    f.write(base64.b64decode(session_data))
                print(f"✅ Восстановлена сессия account_{i}")
            except Exception as e:
                print(f"❌ Ошибка восстановления session_{i}: {e}")

# Вызови функцию сразу после создания папок
restore_sessions()
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import LabeledPrice, PreCheckoutQuery, SuccessfulPayment
from pyrogram import Client
from pyrogram.errors import PhoneNumberInvalid

# ================== НАСТРОЙКИ ==================
TOKEN = "8054814092:AAEVkB2fThqWSL_fwoNFZ7oQ7Dtjwr4wNt0"
ADMIN_ID = 5019414179

PRICE_STARS = 149
DISCOUNT_STARS = 50

# Флаги стран
FLAGS = {
    "us": "🇺🇸", 
    "ru": "🇷🇺", 
    "gb": "🇬🇧",
    "mm": "🇲🇲"
}

# Эмодзи для красоты
EMOJI = {
    "success": "✅", "error": "❌", "wait": "⏳", "money": "💰",
    "star": "⭐", "phone": "📱", "referral": "👥", "support": "📞",
    "help": "❓", "back": "◀️", "code": "🔐", "warning": "⚠️",
    "crown": "👑", "chart": "📊", "time": "⏱️", "lock": "🔒",
    "unlock": "🔓", "discount": "🏷️", "payment": "💳", "link": "🔗",
    "info": "ℹ️", "star2": "✨", "copy": "📋", "arrow": "👉",
    "key": "🔑", "guard": "🛡️", "settings": "⚙️", "check": "✔️",
    "vpn": "🌐", "wait2": "⏰", "alert": "⚠️"
}

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Создаём папки
os.makedirs("sessions", exist_ok=True)
os.makedirs("data", exist_ok=True)

# ================== БАЗА ДАННЫХ SQLITE ==================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('data/bot.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
        print("✅ База данных SQLite инициализирована")
    
    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                ref_code TEXT UNIQUE,
                ref_count INTEGER DEFAULT 0,
                discount INTEGER DEFAULT 0,
                discount_used BOOLEAN DEFAULT 0,
                discount_given BOOLEAN DEFAULT 0,
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
        self.conn.commit()
    
    def add_user(self, user_id):
        try:
            while True:
                ref_code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                self.cursor.execute("SELECT user_id FROM users WHERE ref_code = ?", (ref_code,))
                if not self.cursor.fetchone():
                    break
            
            self.cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, ref_code)
                VALUES (?, ?)
            ''', (user_id, ref_code))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка добавления пользователя: {e}")
            return False
    
    def get_user(self, user_id):
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
                "discount_given": bool(row[5])
            }
        return None
    
    def add_referral(self, referrer_id, referred_id):
        try:
            self.cursor.execute("SELECT id FROM referrals WHERE referred_id = ?", (referred_id,))
            if self.cursor.fetchone():
                return False
            
            if referrer_id == referred_id:
                return False
            
            self.cursor.execute('''
                INSERT INTO referrals (referrer_id, referred_id)
                VALUES (?, ?)
            ''', (referrer_id, referred_id))
            
            self.cursor.execute('''
                UPDATE users 
                SET ref_count = ref_count + 1 
                WHERE user_id = ?
            ''', (referrer_id,))
            
            self.cursor.execute('''
                SELECT ref_count FROM users WHERE user_id = ?
            ''', (referrer_id,))
            ref_count = self.cursor.fetchone()[0]
            
            if ref_count >= 5:
                self.cursor.execute('''
                    UPDATE users 
                    SET discount = ?, discount_given = 1 
                    WHERE user_id = ? AND discount_given = 0
                ''', (DISCOUNT_STARS, referrer_id))
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка добавления реферала: {e}")
            return False
    
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
    
    def get_stats(self):
        stats = {}
        self.cursor.execute("SELECT COUNT(*) FROM users")
        stats['total_users'] = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT COUNT(*) FROM referrals")
        stats['total_refs'] = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT COUNT(*) FROM purchases")
        stats['total_purchases'] = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT SUM(price) FROM purchases")
        total = self.cursor.fetchone()[0]
        stats['total_revenue'] = total if total else 0
        return stats
    
    def close(self):
        self.conn.close()

db = Database()

# ================== БАЗА АККАУНТОВ ==================
accounts = {
    "1": {
        "phone": "+16188550568",
        "country": "us",
        "country_name": "США",
        "api_id": 37379476,
        "api_hash": "67cf40314dc0f31534b4b7feeae39242",
        "session_file": "sessions/account_1",
        "in_use": False,
        "current_user": None,
        "description": "Аккаунт USA, чистый, прогретый"
    },
    "2": {
        "phone": "+15593721842",
        "country": "us",
        "country_name": "США",
        "api_id": 37379476,
        "api_hash": "67cf40314dc0f31534b4b7feeae39242",
        "session_file": "sessions/account_2",
        "in_use": False,
        "current_user": None,
        "description": "Аккаунт USA, чистый, прогретый"
    },
    "3": {
        "phone": "+15399999864",
        "country": "us",
        "country_name": "США",
        "api_id": 37379476,
        "api_hash": "67cf40314dc0f31534b4b7feeae39242",
        "session_file": "sessions/account_3",
        "in_use": False,
        "current_user": None,
        "description": "Аккаунт USA, чистый, прогретый"
    }
}

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

# ================== КЛАСС ДЛЯ ПОЛУЧЕНИЯ КОДА ==================
class CodeGetter:
    def __init__(self, session_file):
        self.session_file = session_file
        print(f"✅ CodeGetter готов для {session_file}")
    
    async def get_code(self, phone, api_id, api_hash):
        """Получает код из чата с Telegram"""
        try:
            print(f"🔄 Подключаюсь к {phone}...")
            
            app = Client(
                name=self.session_file,
                api_id=api_id,
                api_hash=api_hash
            )
            
            await app.start()
            print(f"✅ Успешно подключился!")
            
            # Получаем информацию об аккаунте
            me = await app.get_me()
            print(f"👤 Аккаунт: {me.first_name}")
            
            # Ищем диалог с Telegram
            print("🔍 Ищу диалог с Telegram...")
            telegram_chat_id = None
            
            async for dialog in app.get_dialogs():
                chat = dialog.chat
                if chat.type.value == "private":
                    chat_name = (chat.first_name or "").lower()
                    if "telegram" in chat_name:
                        telegram_chat_id = chat.id
                        print(f"✅ Найден чат: {chat.first_name}")
                        break
            
            if not telegram_chat_id:
                print("❌ Чат Telegram не найден")
                await app.stop()
                return None
            
            # Читаем последние сообщения
            print(f"📨 Читаю сообщения...")
            async for msg in app.get_chat_history(telegram_chat_id, limit=20):
                if msg and msg.text:
                    print(f"📩 {msg.text[:100]}")
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
    
    user = get_user(user_id)
    
    db.cursor.execute("SELECT referrer_id FROM referrals WHERE referred_id = ?", (user_id,))
    is_already_referred = db.cursor.fetchone()
    
    if args and not is_already_referred:
        db.cursor.execute("SELECT user_id FROM users WHERE ref_code = ?", (args,))
        result = db.cursor.fetchone()
        
        if result and result[0] != user_id:
            referrer_id = result[0]
            if db.add_referral(referrer_id, user_id):
                await message.answer(f"{EMOJI['success']} Вы перешли по реферальной ссылке!")
        elif result and result[0] == user_id:
            await message.answer(f"{EMOJI['warning']} Нельзя стать рефералом по своей ссылке!")
    elif args and is_already_referred:
        await message.answer(f"{EMOJI['info']} Вы уже чей-то реферал")
    
    text = (
        f"{EMOJI['phone']} *Добро пожаловать!*\n\n"
        f"{EMOJI['star']} *Цена:* {PRICE_STARS} звёзд\n"
        f"{EMOJI['referral']} *Рефералы:* 5 друзей = скидка {DISCOUNT_STARS} {EMOJI['star']}"
    )
    await message.reply(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# ================== РЕФЕРАЛЫ ==================
@dp.message_handler(lambda msg: msg.text == "👥 Рефералы")
async def referrals(msg: types.Message):
    user = get_user(msg.from_user.id)
    bot_name = (await bot.get_me()).username
    link = f"https://t.me/{bot_name}?start={user['ref_code']}"
    
    progress = "🟩" * user['ref_count'] + "⬜" * (5 - user['ref_count'])
    
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
        f"{EMOJI['arrow']} *Для iPhone:* если ссылка не нажимается, используй кнопку ниже 👇\n\n"
        f"{EMOJI['chart']} *Прогресс:*\n"
        f"{progress}  `{user['ref_count']}/5`\n\n"
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
async def numbers(msg: types.Message):
    await msg.answer("📱 Доступные номера:", reply_markup=get_numbers_keyboard())

@dp.message_handler(lambda msg: msg.text == "📞 Поддержка")
async def support(msg: types.Message):
    await msg.answer("📞 @dan4ezHelp")

@dp.message_handler(lambda msg: msg.text == "❓ Помощь")
async def help_cmd(msg: types.Message):
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

# ================== ВЫБОР НОМЕРА ==================
@dp.callback_query_handler(lambda c: c.data.startswith("num_"))
async def process_number(call: types.CallbackQuery):
    user_id = call.from_user.id
    number = call.data.replace("num_", "")
    
    if number not in accounts:
        await call.message.answer(f"{EMOJI['error']} Аккаунт не найден")
        await call.answer()
        return
    
    account = accounts[number]
    
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
    
    # БЕСПЛАТНО ДЛЯ АДМИНА
    if user_id == ADMIN_ID:
        account["in_use"] = True
        account["current_user"] = user_id
        
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
    
    # ДЛЯ ОБЫЧНЫХ ПОЛЬЗОВАТЕЛЕЙ
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
    
    if number not in accounts:
        return
    
    account = accounts[number]
    
    if account["in_use"]:
        return
    
    account["in_use"] = True
    account["current_user"] = user_id
    
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
            f"Возможно, аккаунт не онлайн. Попробуй через 1-2 минуты или напиши @dan4ezHelp",
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
        status = "✅" if acc["in_use"] else "🟢"
        status_text = "ПРОДАН" if acc["in_use"] else "СВОБОДЕН"
        
        await message.answer(f"📱 *Номер {num}*: {acc['phone']}\nСтатус: {status} {status_text}", parse_mode="Markdown")
        
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
        else:
            results.append(f"⏭️ Номер {num}: пропущен (продан)")
    
    passed = sum(1 for r in results if "✅" in r)
    failed = sum(1 for r in results if "❌" in r)
    skipped = sum(1 for r in results if "⏭️" in r)
    
    final_report = (
        f"📊 *ДИАГНОСТИКА ЗАВЕРШЕНА*\n\n"
        f"✅ Успешно: {passed}\n"
        f"❌ Ошибок: {failed}\n"
        f"⏭️ Пропущено: {skipped}\n"
        f"📱 Всего: {len(accounts)}"
    )
    
    await message.answer(final_report, parse_mode="Markdown")

# ================== СТАТИСТИКА ==================
@dp.message_handler(commands=['stats'])
async def stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    stats = db.get_stats()
    available = sum(1 for acc in accounts.values() if not acc["in_use"])
    sold = sum(1 for acc in accounts.values() if acc["in_use"])
    
    await message.answer(
        f"{EMOJI['chart']} *СТАТИСТИКА*\n\n"
        f"{EMOJI['unlock']} Доступно: {available}\n"
        f"{EMOJI['lock']} Продано: {sold}\n"
        f"👥 Пользователей: {stats['total_users']}\n"
        f"👥 Рефералов: {stats['total_refs']}\n"
        f"💰 Продаж: {stats['total_purchases']}\n"
        f"💎 Всего звезд: {stats['total_revenue']}⭐",
        parse_mode="Markdown"
    )

# ================== ЗАКРЫТИЕ БАЗЫ ==================
atexit.register(db.close)

# ================== ЗАПУСК ==================
if __name__ == '__main__':
    print("=" * 50)
    print("✅ БОТ ЗАПУЩЕН!")
    print("=" * 50)
    print(f"💰 Цена: {PRICE_STARS}⭐")
    print(f"📱 Аккаунтов: {len(accounts)}")
    print("🧪 Тест: /test")
    print("👑 Режим админа: БЕСПЛАТНО")
    print("=" * 50)
    
    executor.start_polling(dp, skip_updates=True)



