FROM python:3.9-slim

# Рабочая директория внутри контейнера
WORKDIR /app

# Копируем только папку app внутрь контейнера
COPY app/ /app/

# Копируем requirements отдельно, если он в корне
COPY requirements.txt /app/

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Запуск бота
CMD ["python", "creatore_di_digest_bot.py"]
