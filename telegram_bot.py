import urllib.parse
import gspread
from fastapi import FastAPI
import uvicorn

# создаем FastAPI-приложение
api_app = FastAPI()

@api_app.get("/ping")
async def ping():
    return {"status": "alive"}

def get_all_month_sheets():
    spreadsheet = gc.open("Автошкола - Запись")
    return [sheet for sheet in spreadsheet.worksheets() if " - 202" in sheet.title and sheet.title != "Архив"]

def append_to_archive():
    spreadsheet = gc.open("Автошкола - Запись")
    try:
        archive = spreadsheet.worksheet("Архив")
    except gspread.exceptions.WorksheetNotFound:
        archive = spreadsheet.add_worksheet("Архив", rows="1000", cols="11")
        archive.append_row([
            "Дата", "Время", "Машина", "Инструктор", "Статус",
            "Имя", "Телефон", "", "Предоплата", "Остаток", "Telegram ID"
        ])

    existing_rows = archive.get_all_values()
    existing_set = set(tuple(row) for row in existing_rows[1:])  # без заголовков

    for sheet in get_all_month_sheets():
        data = sheet.get_all_values()
        for row in data[1:]:  # Пропустить заголовки
            if tuple(row) not in existing_set:
                archive.append_row(row)

import os, json
import datetime

def get_active_sheet_name():
    ru_months = {
        "January": "Январь", "February": "Февраль", "March": "Март",
        "April": "Апрель", "May": "Май", "June": "Июнь",
        "July": "Июль", "August": "Август", "September": "Сентябрь",
        "October": "Октябрь", "November": "Ноябрь", "December": "Декабрь"
    }
    month = datetime.datetime.now().strftime("%B")
    year = datetime.datetime.now().year
    return f"{ru_months[month]} - {year}"

from google.oauth2.service_account import Credentials

# ✅ добавили оба scope'а
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

with open("comisiituairkaz-da1a299ae5c8.json") as f:
    creds_dict = json.load(f)

creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)

gc = gspread.authorize(creds)

import logging
import asyncio
from pytz import timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes, JobQueue
)

logging.basicConfig(level=logging.INFO)

TOKEN = "8055643472:AAE-p7kVsyzHnUeFPgM1hnB7Q1Uu5LebPwQ"

INSTRUCTOR, CAR, DATE, TIME, NAME, PHONE = range(6)

# Шаг 1: выбор инструктора
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [["Серик Молдабаев"], ["Әзгел Беглан"]]
    await update.message.reply_photo(
        photo="https://images2.imgbox.com/96/ac/8W57PB76_o.jpg",
        caption="Серик Молдабаев – автомат"
    )
    await update.message.reply_photo(
        photo="https://images2.imgbox.com/ef/b3/XCTTUIuJ_o.jpg",
        caption="Әзгел Беглан – автомат и механика"
    )
    await update.message.reply_text(
        "Здравствуйте! Выберите инструктора:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return INSTRUCTOR

async def choose_car(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Назад":
        return await start(update, context)

    instructor = update.message.text
    context.user_data["instructor"] = instructor

    if instructor == "Серик Молдабаев":
        reply_keyboard = [["Автомат"], ["Назад"]]
    else:
        reply_keyboard = [["Автомат"], ["Механика"], ["Назад"]]

    await update.message.reply_text("Выберите машину:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return CAR



# Шаг 3: выбор даты
async def choose_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Назад":
        return await choose_car(update, context)

    context.user_data["car"] = update.message.text
    instructor = context.user_data["instructor"]

    records = get_active_sheet().get_all_records()
    available_dates = sorted(list(set(
        row["Дата"] for row in records
        if row["Инструктор"] == instructor and row["Статус"].lower() == "свободно"
    )))

    if not available_dates:
        await update.message.reply_text("Извините, для этого инструктора нет доступных дат.")
        return ConversationHandler.END

    reply_keyboard = [[d] for d in available_dates]
    reply_keyboard.append(["Назад"])

    await update.message.reply_text("Выберите дату урока:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return DATE


# Шаг 4: выбор времени
async def choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Назад":
        return await choose_date(update, context)

    context.user_data["date"] = update.message.text
    instructor = context.user_data["instructor"]
    date = context.user_data["date"]

    records = get_active_sheet().get_all_records()
    available_times = [
        row["Время"] for row in records
        if row["Инструктор"] == instructor and row["Дата"] == date and row["Статус"].lower() == "свободно"
    ]

    if not available_times:
        await update.message.reply_text("На эту дату нет доступного времени.")
        return ConversationHandler.END

    reply_keyboard = [[t] for t in available_times]
    reply_keyboard.append(["Назад"])

    await update.message.reply_text("Выберите время урока:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return TIME



# Шаг 5: имя
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Назад":
        return await choose_time(update, context)

    context.user_data["time"] = update.message.text
    await update.message.reply_text("Введите своё имя:",
                                    reply_markup=ReplyKeyboardMarkup([["Назад"]], one_time_keyboard=True))

    return NAME

# Шаг 6: телефон
async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Назад":
        return await get_name(update, context)

    context.user_data["name"] = update.message.text
    await update.message.reply_text("Введите номер телефона (в формате +7707...):", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], one_time_keyboard=True))
    return PHONE


# Шаг 7: подтверждение
async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Назад":
        return await get_phone(update, context)

    context.user_data["phone"] = update.message.text
    context.user_data["telegram_id"] = update.effective_user.id  # ✅ ШАГ 1 — ВСТАВИТЬ СЮДА

    instructor = context.user_data["instructor"]
    car = context.user_data["car"]
    date = context.user_data["date"]
    time = context.user_data["time"]
    name = context.user_data["name"]
    phone = context.user_data["phone"]

    save_booking_to_sheet(context)

    whatsapp_message = (
        f"Здравствуйте, я {name} записал(-ась) на урок вождения! "
        f"Инструктор: {instructor}, Машина: {car}, Время: {time}, Дата: {date}"
    )

    encoded_message = urllib.parse.quote(whatsapp_message)
    whatsapp_url = f"https://wa.me/77070151513?text={encoded_message}"

    await update.message.reply_text(f"✅ Бронь подтверждена!\n\n"
                                    f"👉 Напишите нам в WhatsApp:\n{whatsapp_url}")
    return ConversationHandler.END

def get_active_sheet():
    sheet = gc.open("Автошкола - Запись")
    sheet_name = get_active_sheet_name()
    try:
        return sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        # Если листа нет — создаём с нужной шапкой
        new_sheet = sheet.add_worksheet(title=sheet_name, rows="1000", cols="11")
        new_sheet.append_row([
            "Дата", "Время", "Машина", "Инструктор", "Статус",
            "Имя", "Телефон", "", "Предоплата", "Остаток", "Telegram ID"
        ])
        return new_sheet


# Сохранение записи только в листе slots
def save_booking_to_sheet(context):
    slots_sheet = get_active_sheet()

    instructor = context.user_data["instructor"]
    car = context.user_data["car"]
    date = context.user_data["date"]
    time = context.user_data["time"]
    name = context.user_data["name"]
    phone = context.user_data["phone"]
    telegram_id = context._user_id  # ⚠️ Telegram ID

    records = slots_sheet.get_all_records()
    for i, row in enumerate(records):
        if row["Инструктор"] == instructor and row["Дата"] == date and row["Время"] == time:
            row_num = i + 2  # строка, в которую пишем

            # Обновляем поля
            slots_sheet.update_cell(row_num, 3, car)        # Машина (C)
            slots_sheet.update_cell(row_num, 5, "занято")   # Статус (E)
            slots_sheet.update_cell(row_num, 6, name)       # Имя (F)
            slots_sheet.update_cell(row_num, 7, phone)      # Телефон (G)
            slots_sheet.update_cell(row_num, 11, telegram_id)  # ✅ Telegram ID (K, колонка №11)
            break


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бронь остановлена.")
    return ConversationHandler.END

async def archive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        append_to_archive()
        await update.message.reply_text("📦 Архив успешно обновлён!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при архивации: {e}")

async def monitor_payments(application):
    await asyncio.sleep(10)
    sheet = get_active_sheet()
    previous = sheet.get_all_records()

    while True:
        await asyncio.sleep(30)
        current = sheet.get_all_records()

        for i, row in enumerate(current):
            if i >= len(previous):
                continue

            prev = previous[i]
            telegram_id = row.get("Telegram ID")
            if not telegram_id:
                continue

            try:
                telegram_id = int(telegram_id)
            except ValueError:
                continue

            pre_now = str(row.get("Предоплата", "") or "").strip()
            pre_prev = str(prev.get("Предоплата", "") or "").strip()
            ost_now = str(row.get("Остаток", "") or "").strip()
            ost_prev = str(prev.get("Остаток", "") or "").strip()

            # Получаем дату урока
            lesson_date = row.get("Дата")  # замени на точное имя столбца в таблице
            formatted_date = f" на урок вождения {lesson_date}" if lesson_date else ""

            # ✅ Предоплата добавлена
            if pre_now and not pre_prev:
                await application.bot.send_message(
                    chat_id=telegram_id,
                    text=f"✅ Ваша предоплата: {pre_now}₸{formatted_date}"
                )

            # ✅ Остаток добавлен
            if ost_now and not ost_prev:
                await application.bot.send_message(
                    chat_id=telegram_id,
                    text=f"✅ Ваш остаток: {ost_now}₸{formatted_date}"
                )

        previous = current



async def on_startup(application):
    application.create_task(monitor_payments(application))

# Основная функция
def main():
    scheduler = AsyncIOScheduler(timezone=timezone("Asia/Almaty"))
    job_queue = JobQueue()
    job_queue.scheduler = scheduler

    app = ApplicationBuilder().token(TOKEN).job_queue(job_queue).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            INSTRUCTOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_car)],
            CAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_date)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_time)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)

    async def post_init(application):
        application.create_task(monitor_payments(application))

    app.post_init = post_init

    # 🔥 запустить и FastAPI, и Telegram-бот
    import threading
    threading.Thread(target=lambda: uvicorn.run(api_app, host="0.0.0.0", port=8000)).start()

    app.run_polling()


if __name__ == "__main__":
    main()

