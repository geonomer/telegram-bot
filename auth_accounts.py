# -*- coding: utf-8 -*-
import asyncio
import os
import base64
from pyrogram import Client

# ================== НАСТРОЙКИ ==================
API_ID = 37379476
API_HASH = "67cf40314dc0f31534b4b7feeae39242"

# Список аккаунтов для авторизации
ACCOUNTS = [
    {"num": 1, "phone": "+16188550568"},
    {"num": 2, "phone": "+15593721842"},
    {"num": 3, "phone": "+15399999864"},
]

async def auth_account(num, phone):
    """Авторизует один аккаунт и возвращает base64 сессии"""
    print(f"\n🔄 Авторизация аккаунта {num}: {phone}")
    
    session_file = f"sessions/account_{num}"
    
    app = Client(
        name=session_file,
        api_id=API_ID,
        api_hash=API_HASH,
        phone_number=phone
    )
    
    try:
        await app.start()
        me = await app.get_me()
        print(f"✅ Аккаунт {num} авторизован! ID: {me.id}, Имя: {me.first_name}")
        
        # Читаем файл сессии и конвертируем в base64
        with open(f"{session_file}.session", "rb") as f:
            session_data = f.read()
            base64_data = base64.b64encode(session_data).decode('utf-8')
            print(f"\n🔐 SESSION_{num} = {base64_data}")
            print("-" * 80)
        
        await app.stop()
        return base64_data
    except Exception as e:
        print(f"❌ Ошибка авторизации аккаунта {num}: {e}")
        return None

async def main():
    """Авторизует все аккаунты"""
    print("=" * 50)
    print("🚀 АВТОРИЗАЦИЯ АККАУНТОВ")
    print("=" * 50)
    
    # Создаём папку для сессий
    os.makedirs("sessions", exist_ok=True)
    
    all_sessions = []
    for acc in ACCOUNTS:
        session = await auth_account(acc["num"], acc["phone"])
        if session:
            all_sessions.append(session)
        await asyncio.sleep(2)  # Пауза между аккаунтами
    
    print("\n✅ Всего авторизовано:", len(all_sessions))
    print("\n📋 Скопируй эти строки в переменные окружения Render:")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
