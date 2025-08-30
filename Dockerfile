FROM python:3.11-slim

# Установка системных пакетов
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копируем зависимости
COPY requirements.txt /app/

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY creatore_di_digest_bot.py /app/

# Запуск бота
CMD ["python", "creatore_di_digest_bot.py"]