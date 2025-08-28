# Используем официальный образ Python как базовый.
# Выбираем версию 3.11 и slim для уменьшения размера образа.
FROM python:3.11-slim

# Установка системных пакетов
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию внутри контейнера.
# Все последующие команды будут выполняться относительно этой директории.
WORKDIR /app

# Копируем файл requirements.txt в рабочую директорию.
# Это делается первым, чтобы Docker мог кэшировать этот слой.
COPY requirements.txt /app/

# Устанавливаем зависимости из requirements.txt.
# Используем --no-cache-dir для экономии места.
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код бота в рабочую директорию.
COPY . /app/

# Запуск бота
CMD ["python", "Creatore_di_Digest_bot.py"]
