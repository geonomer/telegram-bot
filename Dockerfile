# Используем официальный базовый образ Python 3.8
FROM python:3.8-slim

# Устанавливаем системные зависимости, необходимые для сборки некоторых Python-пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Создаём рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код бота в контейнер
COPY . .

# Указываем команду для запуска бота
CMD ["python", "bot.py"]
