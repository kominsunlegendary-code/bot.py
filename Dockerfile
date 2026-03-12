FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

COPY bot.py .

RUN pip install --no-cache-dir \
    PyMuPDF==1.24.1 \
    python-telegram-bot==21.3

CMD ["python", "bot.py"]
