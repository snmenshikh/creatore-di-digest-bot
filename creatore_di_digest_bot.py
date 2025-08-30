import os
import pandas as pd
import tempfile
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from telethon import TelegramClient
from docx import Document
import nltk
from nltk.tokenize import sent_tokenize

# -----------------------------
# NLTK
# -----------------------------
nltk.download("punkt")
nltk.download("stopwords")

# -----------------------------
# Получение API данных из переменных окружения
# -----------------------------
api_id = os.getenv("TELEGRAM_API_ID")
api_hash = os.getenv("TELEGRAM_API_HASH")

# -----------------------------
# Conversation states
# -----------------------------
WAITING_FOR_FILE = 1
WAITING_FOR_INTERVAL = 2
WAITING_FOR_CUSTOM_INTERVAL_FROM = 3
WAITING_FOR_CUSTOM_INTERVAL_TO = 4
WAITING_FOR_KEYWORDS = 5
WAITING_FOR_PHONE = 6  # Состояние для запроса номера телефона

# -----------------------------
# Start & cancel handlers
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Пожалуйста, отправьте свой номер телефона (с кодом страны, например, +1234567890).")
    return WAITING_FOR_PHONE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Неизвестная команда. Используйте /start для начала.")

# -----------------------------
# Request phone number
# -----------------------------
async def request_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пожалуйста, отправьте свой номер телефона (с кодом страны, например, +1234567890):")
    return WAITING_FOR_PHONE

async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone_number = update.message.text.strip()
    if phone_number:
        # Создаем и запускаем TelegramClient
        client = TelegramClient('session_name', int(api_id), api_hash)
        await client.start(phone=phone_number)  # Авторизация через номер телефона
        await update.message.reply_text("Телефон успешно зарегистрирован!")

        # Сохраняем клиент для дальнейшего использования
        context.user_data["client"] = client

        # Переходим к следующему шагу: загрузка файла
        return WAITING_FOR_FILE
    else:
        await update.message.reply_text("Пожалуйста, отправьте действительный номер телефона.")
        return WAITING_FOR_PHONE

# -----------------------------
# Handle Excel file
# -----------------------------
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document:
        await update.message.reply_text("Пожалуйста, загрузите Excel-файл.")
        return WAITING_FOR_FILE

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tg_file = await document.get_file()
        await tg_file.download_to_drive(tf.name)
        file_path = tf.name

    ext = os.path.splitext(document.file_name)[-1].lower()
    try:
        if ext == ".xlsx":
            df = pd.read_excel(file_path, engine="openpyxl")
        elif ext == ".xls":
            df = pd.read_excel(file_path, engine="xlrd")
        else:
            await update.message.reply_text("Неподдерживаемый формат. Используйте .xls или .xlsx")
            return WAITING_FOR_FILE
    except Exception as e:
        await update.message.reply_text(f"Ошибка при чтении Excel: {e}")
        return WAITING_FOR_FILE

    context.user_data["channels"] = df

    keyboard = [
        [InlineKeyboardButton("Сутки", callback_data="interval_day")],
        [InlineKeyboardButton("Неделя", callback_data="interval_week")],
        [InlineKeyboardButton("Месяц", callback_data="interval_month")],
        [InlineKeyboardButton("Задайте произвольный интервал", callback_data="interval_custom")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите интервал времени:", reply_markup=reply_markup)
    return WAITING_FOR_INTERVAL

# -----------------------------
# Interval handlers
# -----------------------------
async def interval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.replace("interval_", "")
    if data == "custom":
        await query.edit_message_text("Введите дату начала интервала (ГГГГ-ММ-ДД):")
        return WAITING_FOR_CUSTOM_INTERVAL_FROM
    else:
        context.user_data["interval"] = data
        await query.edit_message_text("Введите ключевые слова (через запятую):")
        return WAITING_FOR_KEYWORDS

async def custom_interval_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["custom_from"] = update.message.text.strip()
    await update.message.reply_text("Введите дату окончания интервала (ГГГГ-ММ-ДД):")
    return WAITING_FOR_CUSTOM_INTERVAL_TO

async def custom_interval_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    custom_from = context.user_data.get("custom_from")
    custom_to = update.message.text.strip()
    context.user_data["interval"] = (custom_from, custom_to)
    await update.message.reply_text("Введите ключевые слова (через запятую):")
    return WAITING_FOR_KEYWORDS

# -----------------------------
# Generate digest
# -----------------------------
async def handle_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keywords = [k.strip() for k in update.message.text.split(",") if k.strip()]
    context.user_data["keywords"] = keywords

    await update.message.reply_text(
        "Файл принят ✅\nИнтервал задан ✅\nКлючевые слова сохранены ✅\n\nГотовлю дайджест...",
        reply_markup=ReplyKeyboardRemove()
    )

    digest_path = await generate_digest(context.user_data)

    if digest_path and os.path.exists(digest_path):
        await update.message.reply_document(open(digest_path, "rb"), filename="digest.docx")
    else:
        await update.message.reply_text("Не удалось создать дайджест 😢")

    return ConversationHandler.END

# -----------------------------
# Telegram post fetching + summarization
# -----------------------------
async def get_posts(client, channel_link, interval):
    await client.start()
    channel = await client.get_entity(channel_link)
    now = datetime.utcnow()

    if interval == "day":
        start_date = now - timedelta(days=1)
    elif interval == "week":
        start_date = now - timedelta(weeks=1)
    elif interval == "month":
        start_date = now - timedelta(days=30)
    elif isinstance(interval, tuple):
        start_date = datetime.fromisoformat(interval[0])
        end_date = datetime.fromisoformat(interval[1])
    else:
        start_date = now - timedelta(days=1)
    end_date = now if not isinstance(interval, tuple) else end_date

    posts_text = []
    async for message in client.iter_messages(channel, offset_date=end_date, reverse=True):
        if message.date < start_date:
            break
        if message.text:
            posts_text.append((message.date, message.text))
    return posts_text

def summarize_text(text, keywords=None):
    sentences = sent_tokenize(text)
    if keywords:
        keywords = [k.lower() for k in keywords]
        filtered = [s for s in sentences if any(k in s.lower() for k in keywords)]
        return "\n".join(filtered[:5])
    else:
        return "\n".join(sentences[:5])

async def generate_digest(user_data):
    channels = user_data.get("channels")
    interval = user_data.get("interval")
    keywords = user_data.get("keywords", [])

    if channels is None or not keywords:
        return None

    client = user_data.get("client")  # Используем уже авторизованный client

    digest_text = "📌 Дайджест по вашим каналам:\n\n"

    for _, row in channels.iterrows():
        channel_name = row[0]
        channel_link = row[1]
        posts = await get_posts(client, channel_link, interval)
        if not posts:
            digest_text += f"{channel_name} ({channel_link}): Нет сообщений за этот интервал\n"
            continue
        digest_text += f"--- {channel_name} ({channel_link}) ---\n"
        for date, text in posts:
            if text:
                summary = summarize_text(text, keywords)
                digest_text += f"{date.date()}: {summary}\n"
            else:
                digest_text += f"{date.date()}: (Пустое сообщение)\n"

    output_dir = "/app/data"
    os.makedirs(output_dir, exist_ok=True)
    digest_path = os.path.join(output_dir, "digest.docx")

    doc = Document()
    doc.add_heading("Дайджест", 0)
    doc.add_paragraph(digest_text)
    doc.save(digest_path)

    return digest_path

# -----------------------------
# Main
# -----------------------------
async def main():
    # Строим и запускаем приложение с учетом того, что цикл событий уже работает в run_polling
    application = ApplicationBuilder().token(os.getenv("TELEGRAM_API_TOKEN")).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number)],
            WAITING_FOR_FILE: [MessageHandler(filters.Document.ALL, handle_file)],
            WAITING_FOR_INTERVAL: [CallbackQueryHandler(interval_callback, pattern=r"^interval_")],
            WAITING_FOR_CUSTOM_INTERVAL_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_interval_from)],
            WAITING_FOR_CUSTOM_INTERVAL_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_interval_to)],
            WAITING_FOR_KEYWORDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keywords)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    # Запускаем бота в режиме polling
    await application.run_polling()

# Если скрипт запускается напрямую, вызываем main
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())  # Запуск основного потока с asyncio