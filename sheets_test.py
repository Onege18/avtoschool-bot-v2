import gspread
import os
from oauth2client.service_account import ServiceAccountCredentials

# Области доступа
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Путь до JSON-файла ключа
json_path = os.path.join(os.path.dirname(__file__), "comisiituairkaz-da1a299ae5c8.json")

# Авторизация
creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
client = gspread.authorize(creds)

# Открытие таблицы
spreadsheet = client.open("Автошкола - Запись")


# 🔹 Получить доступные слоты по инструктору
def get_available_slots_for_instructor(instructor):
    sheet = spreadsheet.worksheet("slots")
    all_slots = sheet.get_all_records()

    available = [
        slot for slot in all_slots
        if slot["Инструктор"] == instructor and slot["Статус"].lower() == "свободно"
    ]

    return available


# 🔹 Добавить бронь в slots (без bookings)
def add_booking(client_name, phone, date, time, instructor):
    slots = spreadsheet.worksheet("slots")
    rows = slots.get_all_records()
    row_index = None

    for i, row in enumerate(rows):
        if (
            row["Дата"] == date and
            row["Время"] == time and
            row["Инструктор"] == instructor and
            row["Статус"].lower() == "свободно"
        ):
            row_index = i + 2  # +2 — чтобы учесть заголовки
            break

    if not row_index:
        print("❌ Слот не найден или уже занят")
        return

    # Обновить слот:
    slots.update_cell(row_index, 5, "занято")       # Статус (E)
    slots.update_cell(row_index, 6, client_name)    # Имя клиента (F)
    slots.update_cell(row_index, 7, phone)          # Телефон (G)

    print("✅ Бронь успешно добавлена в слот")


# 🔹 Пример использования:

instructor = "Серик Молдабаев"

print(f"👉 Доступные слоты для: {instructor}")
slots = get_available_slots_for_instructor(instructor)
for slot in slots:
    print(f"{slot['Дата']} | {slot['Время']} | {slot['Машина']}")

# Пример бронирования:
add_booking(
    client_name="Айгерим Калыбек",
    phone="+77070005522",
    date="08.06.2025",
    time="09:30 – 11:00",
    instructor="Серик Молдабаев"
)
