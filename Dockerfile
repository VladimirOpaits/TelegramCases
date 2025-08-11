# Используем Python образ с поддержкой Rust
FROM python:3.11-slim as python-builder

# Устанавливаем Rust и системные зависимости
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Копируем requirements.txt
COPY requirements.txt .

# Устанавливаем Python зависимости (включая те, что требуют Rust)
RUN pip install --no-cache-dir -r requirements.txt

# Создаем финальный образ
FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем установленные Python пакеты
COPY --from=python-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем код приложения
COPY . .

# Создаем необходимые директории
RUN mkdir -p temp logs

# Открываем порт
EXPOSE 8000

# Команда запуска
CMD ["python", "main.py"] 