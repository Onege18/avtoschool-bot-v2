from dotenv import load_dotenv
load_dotenv()

import os
import json
import asyncio
import logging
import datetime
import urllib.parse

import gspread
from google.oauth2.service_account import Credentials

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from pytz import timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes, JobQueue
)

# === Настройка логирования ===
logging.basicConfig(level=logging.INFO)

# === Переменные окружения ===
TOKEN = os.getenv("TOKEN")
creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])

# === Авторизация Google Sheets ===
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)

# === FastAPI и Telegram ===
api_app = FastAPI()
telegram_app: Application = None

# === Константы ===
INSTRUCTOR, CAR, DATE, TIME, NAME, PHONE = range(6)

# === Утилиты ===
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

def get_active_sheet():
    sheet = gc.open("Автошкола - NS Запись")
    sheet_name = get_active_sheet_name()
    try:
        return sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        new_sheet = sheet.add_worksheet(title=sheet_name, rows="1000", cols="11")
        new_sheet.append_row([
            "Дата", "Время", "Машина", "Инструктор", "Статус",
            "Имя", "Телефон", "", "Предоплата", "Остаток", "Telegram ID"
        ])
        return new_sheet

def save_booking_to_sheet(context):
    sheet = get_active_sheet()
    data = context.user_data
    records = sheet.get_all_records()
    for i, row in enumerate(records):
        if row["Инструктор"] == data["instructor"] and row["Дата"] == data["date"] and row["Время"] == data["time"]:
            row_num = i + 2
            sheet.update_cell(row_num, 3, data["car"])
            sheet.update_cell(row_num, 5, "занято")
            sheet.update_cell(row_num, 6, data["name"])
            sheet.update_cell(row_num, 7, data["phone"])
            sheet.update_cell(row_num, 11, context._user_id)
            break

# === Хендлеры Telegram ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [["Серик Молдабаев"], ["Әзгел Беглан"]]
    await update.message.reply_photo("https://images2.imgbox.com/96/ac/8W57PB76_o.jpg", caption="Серик Молдабаев – автомат")
    await update.message.reply_photo("https://images2.imgbox.com/ef/b3/XCTTUIuJ_o.jpg", caption="Әзгел Беглан – автомат и механика")
    await update.message.reply_text("Здравствуйте! Выберите инструктора:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return INSTRUCTOR

async def choose_car(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Назад":
        return await start(update, context)
    instructor = update.message.text
    context.user_data["instructor"] = instructor
    reply_keyboard = [["Автомат"], ["Механика"]] if instructor != "Серик Молдабаев" else [["Автомат"]]
    reply_keyboard.append(["Назад"])
    await update.message.reply_text("Выберите машину:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return CAR

async def choose_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Назад":
        return await choose_car(update, context)
    context.user_data["car"] = update.message.text
    instructor = context.user_data["instructor"]
    records = get_active_sheet().get_all_records()
    dates = sorted(set(r["Дата"] for r in records if r["Инструктор"] == instructor and r["Статус"].lower() == "свободно"))
    if not dates:
        await update.message.reply_text("Нет доступных дат.")
        return ConversationHandler.END
    await update.message.reply_text("Выберите дату:", reply_markup=ReplyKeyboardMarkup([[d] for d in dates] + [["Назад"]], one_time_keyboard=True))
    return DATE

async def choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Назад":
        return await choose_date(update, context)
    context.user_data["date"] = update.message.text
    instructor, date = context.user_data["instructor"], context.user_data["date"]
    records = get_active_sheet().get_all_records()
    times = [r["Время"] for r in records if r["Инструктор"] == instructor and r["Дата"] == date and r["Статус"].lower() == "свободно"]
    if not times:
        await update.message.reply_text("Нет доступного времени.")
        return ConversationHandler.END
    await update.message.reply_text("Выберите время:", reply_markup=ReplyKeyboardMarkup([[t] for t in times] + [["Назад"]], one_time_keyboard=True))
    return TIME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Назад":
        return await choose_time(update, context)
    context.user_data["time"] = update.message.text
    await update.message.reply_text("Введите имя:", reply_markup=ReplyKeyboardMarkup([["Назад"]], one_time_keyboard=True))
    return NAME

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Назад":
        return await get_name(update, context)
    context.user_data["name"] = update.message.text
    await update.message.reply_text("Введите номер телефона:", reply_markup=ReplyKeyboardMarkup([["Назад"]], one_time_keyboard=True))
    return PHONE

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Назад":
        return await get_phone(update, context)
    context.user_data["phone"] = update.message.text
    context.user_data["telegram_id"] = update.effective_user.id
    save_booking_to_sheet(context)
    msg = f"Здравствуйте, я {context.user_data['name']} записал(-ась) на урок вождения! Инструктор: {context.user_data['instructor']}, Машина: {context.user_data['car']}, Время: {context.user_data['time']}, Дата: {context.user_data['date']}"
    encoded = urllib.parse.quote(msg)
    url = f"https://wa.me/77070151513?text={encoded}"
    await update.message.reply_text(f"✅ Бронь подтверждена!\n\n👉 WhatsApp: {url}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бронь отменена.")
    return ConversationHandler.END

# === Мониторинг предоплат ===
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
            tg_id = row.get("Telegram ID")
            if not tg_id:
                continue
            try:
                tg_id = int(tg_id)
            except ValueError:
                continue
            if row.get("Предоплата") and not prev.get("Предоплата"):
                await application.bot.send_message(chat_id=tg_id, text=f"✅ Ваша предоплата: {row['Предоплата']}₸")
            if row.get("Остаток") and not prev.get("Остаток"):
                await application.bot.send_message(chat_id=tg_id, text=f"✅ Ваш остаток: {row['Остаток']}₸")
        previous = current

# === FastAPI /ping endpoint для Railway ===
@api_app.get("/ping")
def ping():
    return {"status": "ok"}

@api_app.head("/ping")
def ping_head():
    return JSONResponse(status_code=200)

# === Запуск при старте ===
@api_app.on_event("startup")
async def startup_event():
    global telegram_app
    scheduler = AsyncIOScheduler(timezone=timezone("Asia/Almaty"))
    job_queue = JobQueue()
    job_queue.scheduler = scheduler

    telegram_app = ApplicationBuilder().token(TOKEN).job_queue(job_queue).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            INSTRUCTOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_car)],
            CAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_date)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_time)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    telegram_app.add_handler(conv_handler)
    await telegram_app.initialize()
    telegram_app.create_task(monitor_payments(telegram_app))
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    print("✅ Бот и сервер запущены.")
