import os
import pandas as pd
from telethon import TelegramClient
import nltk
from nltk.tokenize import sent_tokenize
from nltk.corpus import stopwords
from docx import Document
from apscheduler.schedulers.blocking import BlockingScheduler
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ReplyKeyboardMarkup
import datetime

# Загрузка необходимых ресурсов для nltk
nltk.download('punkt')
nltk.download('stopwords')

# Получаем токены из переменных окружения
API_ID = os.getenv("TELETHON_API_ID")
API_HASH = os.getenv("TELETHON_API_HASH")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Настройка клиента Telethon
client = TelegramClient('bot', API_ID, API_HASH)

# Функция для безопасного хранения токенов (уже используется в Portainer через environment переменные)
def get_tokens_from_env():
    return {
        "api_id": os.getenv("API_ID"),
        "api_hash": os.getenv("API_HASH"),
        "bot_token": os.getenv("BOT_TOKEN")
    }

# Функция для обработки Excel файла
def validate_excel(file_path):
    try:
        # Загружаем файл Excel
        df = pd.read_excel(file_path)

        # Проверяем, что в таблице есть нужные столбцы
        required_columns = ['Имя канала', 'Адрес канала']
        if not all(col in df.columns for col in required_columns):
            raise ValueError("Excel файл должен содержать столбцы: 'Имя канала' и 'Адрес канала'")

        return df
    except Exception as e:
        print(f"Ошибка при обработке Excel файла: {e}")
        return None

# Функция для фильтрации сообщений по тегам
def filter_messages(messages, keywords):
    filtered_messages = []
    for message in messages:
        if any(keyword.lower() in message.text.lower() for keyword in keywords):
            filtered_messages.append(message)
    return filtered_messages

# Функция для создания дайджеста и сохранения его в .docx
def create_digest(messages, filename="digest.docx"):
    doc = Document()
    doc.add_heading('Дайджест сообщений', 0)

    for msg in messages:
        doc.add_paragraph(f"{msg.sender_id}: {msg.text}")
        doc.add_paragraph(f"Источник: [ссылка на канал](https://t.me/{msg.sender_id})")
        doc.add_paragraph(f"Дата: {msg.date.strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")

    doc.save(filename)

# Функция для обработки команды /start
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("Привет! Пожалуйста, отправьте мне Excel файл с каналами.")

# Функция для обработки полученного файла
async def handle_file(update: Update, context: CallbackContext):
    file = update.message.document.get_file()
    file.download('channels.xlsx')
    channels_df = validate_excel('channels.xlsx')

    if channels_df is None:
        await update.message.reply_text("Произошла ошибка при обработке файла.")
        return

    await update.message.reply_text("Файл успешно загружен. Укажите интервал для дайджеста.")

# Функция для выбора интервала
async def choose_interval(update: Update, context: CallbackContext):
    keyboard = [
        ['Сутки', 'Неделя', 'Месяц'],
        ['Произвольный интервал']
    ]
    await update.message.reply_text('Выберите интервал для дайджеста:', reply_markup=ReplyKeyboardMarkup(keyboard))

# Функция для отправки дайджеста (по расписанию)
def scheduled_task():
    print("Отправка регулярного дайджеста")

# Планируем задачу на утро (например, каждый день в 9 утра)
scheduler = BlockingScheduler()
scheduler.add_job(scheduled_task, 'interval', days=1, start_date='2025-08-31 09:00:00')

scheduler.start()

# Функция для запуска бота
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    application.add_handler(MessageHandler(filters.TEXT, choose_interval))

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()