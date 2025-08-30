import os
import logging
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from apscheduler.schedulers.background import BackgroundScheduler
import openpyxl
import nltk
from nltk.corpus import stopwords
from docx import Document
from telegram.ext import PicklePersistence

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка NLTK
nltk.download('punkt')
nltk.download('stopwords')

# Секреты из переменных окружения
telethon_api_id = os.getenv("telethon_api_id")
telethon_api_hash = os.getenv("telethon_api_hash")
telegram_bot_token = os.getenv("telegram_bot_token")

# Строки для хранения токенов
client = TelegramClient('bot', telethon_api_id, telethon_api_hash)

# Функция для обработки ошибок Excel
def validate_excel(file):
    try:
        wb = openpyxl.load_workbook(file)
        sheet = wb.active
        headers = [cell.value for cell in sheet[1]]
        if 'Имя канала' in headers and 'Адрес канала' in headers:
            return True
        else:
            raise ValueError("Ошибка в файле: отсутствуют нужные столбцы.")
    except Exception as e:
        logger.error(f"Ошибка при обработке Excel: {e}")
        return False

# Функция для создания дайджеста
def create_digest(update, context, channels, time_period, keywords):
    client.start()
    document = Document()
    document.add_heading('Дайджест из каналов', 0)

    for name, link in channels:
        # Получаем сообщения из канала
        channel = client.get_entity(link)
        history = client(GetHistoryRequest(
            peer=channel,
            limit=100,
            offset_id=0,
            add_offset=0,
            max_id=0,
            min_id=0,
            hash=0
        ))
        
        messages = history.messages
        for message in messages:
            if any(keyword.lower() in message.text.lower() for keyword in keywords):
                doc = document.add_paragraph()
                doc.add_run(f"{message.date} | {name} ({link})\n")
                doc.add_run(f"{message.text}\n\n")
    
    document.save("digest.docx")
    update.message.reply_document(document=open('digest.docx', 'rb'))

# Функция обработки команды /start
def start(update: Update, context):
    update.message.reply_text('Здравствуйте! Отправьте Excel файл с каналами.')
    return

# Функция для обработки файла
def handle_file(update: Update, context):
    user = update.message.from_user
    file = update.message.document.get_file()
    file.download('channels.xlsx')

    if validate_excel('channels.xlsx'):
        update.message.reply_text('Файл принят. Укажите интервал времени для дайджеста.')
        # Вставим кнопки для выбора интервала времени
        keyboard = [
            ['Сутки', 'Неделя', 'Месяц', 'Произвольный интервал']
        ]
        reply_markup = {'keyboard': keyboard, 'resize_keyboard': True}
        update.message.reply_text('Выберите интервал времени:', reply_markup=reply_markup)
    else:
        update.message.reply_text('Неверный формат файла. Убедитесь, что есть столбцы "Имя канала" и "Адрес канала".')

# Функция для обработки интервала времени
def handle_time_interval(update: Update, context):
    interval = update.message.text
    # Здесь можно добавить выбор интервала времени
    channels = []
    wb = openpyxl.load_workbook('channels.xlsx')
    sheet = wb.active
    for row in sheet.iter_rows(min_row=2, values_only=True):
        channels.append((row[0], row[1]))  # Имя канала и Адрес канала

    # Сохраняем ключевые слова
    update.message.reply_text("Введите ключевые слова (через запятую) для поиска в сообщениях.")
    return

# Функция для обработки ключевых слов
def handle_keywords(update: Update, context):
    keywords = update.message.text.split(',')
    update.message.reply_text("Подготовка дайджеста...")
    create_digest(update, context, channels, interval, keywords)
    return

# Планировщик для регулярной отправки дайджестов
def send_regular_digest():
    scheduler = BackgroundScheduler()
    scheduler.add_job(create_digest, 'interval', hours=24)
    scheduler.start()

# Главная функция для запуска бота
def main():
    updater = Updater(token=telegram_bot_token, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.document.mime_type("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"), handle_file))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_time_interval))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_keywords))

    send_regular_digest()

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()