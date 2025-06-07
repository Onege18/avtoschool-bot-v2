import urllib.parse
import gspread
import os, json
from google.oauth2.service_account import Credentials

# ✅ добавили оба scope'а
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)
sheet = gc.open("Автошкола - Запись").worksheet("slots")

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [["Серик Молдабаев"], ["Әзгел Беглан"]]
    await update.message.reply_photo(
        photo="https://images2.imgbox.com/96/ac/8W57PB76_o.jpg",
        caption="Серик Молдабаев – механика"
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
    instructor = update.message.text
    context.user_data["instructor"] = instructor

    if instructor == "Серик Молдабаев":
        reply_keyboard = [["Автомат"]]
    else:
        reply_keyboard = [["Автомат"], ["Механика"]]

    await update.message.reply_text("Выберите машину:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return CAR


async def choose_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["car"] = update.message.text
    instructor = context.user_data["instructor"]

    # Получаем все строки
    records = sheet.get_all_records()

    # Фильтруем по выбранному инструктору и статусу
    available_dates = sorted(list(set(
        row["Дата"] for row in records
        if row["Инструктор"] == instructor and row["Статус"].lower() == "свободно"
    )))

    if not available_dates:
        await update.message.reply_text("Извините, для этого инструктора нет доступных дат.")
        return ConversationHandler.END

    reply_keyboard = [[d] for d in available_dates]
    await update.message.reply_text("Выберите дату урока:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return DATE


async def choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["date"] = update.message.text
    instructor = context.user_data["instructor"]
    date = context.user_data["date"]

    records = sheet.get_all_records()

    available_times = [
        row["Время"] for row in records
        if row["Инструктор"] == instructor and row["Дата"] == date and row["Статус"].lower() == "свободно"
    ]

    if not available_times:
        await update.message.reply_text("На эту дату нет доступного времени.")
        return ConversationHandler.END

    reply_keyboard = [[t] for t in available_times]
    await update.message.reply_text("Выберите время урока:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return TIME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["time"] = update.message.text
    await update.message.reply_text("Введите своё имя:")
    return NAME

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("Введите номер телефона (в формате +7707...):")
    return PHONE


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text

    instructor = context.user_data["instructor"]
    car = context.user_data["car"]
    date = context.user_data["date"]
    time = context.user_data["time"]
    name = context.user_data["name"]
    phone = context.user_data["phone"]

    # 💾 сохраняем в bookings
    save_booking_to_sheet(context)

    # 📞 создаём WhatsApp ссылку
    whatsapp_message = (
        f"Здравствуйте, я {name} записал(-ась) на урок вождения! "
        f"Инструктор: {instructor}, Время: {time}, Дата: {date}"
    )

    encoded_message = urllib.parse.quote(whatsapp_message)
    whatsapp_url = f"https://wa.me/77070151513?text={encoded_message}"

    await update.message.reply_text(f"✅ Бронь подтверждена!\n\n"
                                    f"👉 Напишите нам в WhatsApp:\n{whatsapp_url}")

    return ConversationHandler.END


def save_booking_to_sheet(context):
    booking_sheet = gc.open("Автошкола - Запись").worksheet("bookings")
    slots_sheet = gc.open("Автошкола - Запись").worksheet("slots")

    instructor = context.user_data["instructor"]
    car = context.user_data["car"]
    date = context.user_data["date"]
    time = context.user_data["time"]
    name = context.user_data["name"]
    phone = context.user_data["phone"]

    # 1. Добавляем запись в bookings
    booking_sheet.append_row([name, instructor, car, date, time, phone])

    # 2. Обновляем статус в slots
    records = slots_sheet.get_all_records()
    for i, row in enumerate(records):
        if row["Инструктор"] == instructor and row["Дата"] == date and row["Время"] == time:
            cell_row = i + 2  # +2, потому что get_all_records пропускает заголовок (первая строка)
            slots_sheet.update_cell(cell_row, 5, "занято")  # колонка E (5-я)
            break


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бронь остановлена.")
    return ConversationHandler.END

def main():
    from pytz import timezone
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from telegram.ext import JobQueue

    # 1. Создаём таймзону
    scheduler = AsyncIOScheduler(timezone=timezone("Asia/Almaty"))

    # 2. Создаём job_queue с заданным scheduler (НЕ запускаем вручную!)
    job_queue = JobQueue()
    job_queue.scheduler = scheduler

    # 3. Собираем приложение
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
    app.run_polling()


if __name__ == "__main__":
    main()


