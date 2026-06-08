# ============================================================
#  Exile Eye Navigator - Dockerfile fuers Hosting
#  Installiert Python + Tesseract (Deutsch + Englisch) automatisch.
# ============================================================
FROM python:3.12-slim

# Tesseract-OCR mit deutschem UND englischem Sprachpaket installieren
# + Bibliotheken die OpenCV/Pillow brauchen
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-deu \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Erst nur requirements kopieren (besseres Caching beim Bauen)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Dann den Rest des Codes
COPY . .

# Tesseract liegt auf Linux hier:
ENV TESSERACT_PATH=/usr/bin/tesseract
# Produktionsmodus (sichere Cookies, keine Fehler-Details)
ENV FLASK_DEBUG=0

# Hosting-Anbieter geben den Port per $PORT vor (Default 8000)
ENV PORT=8000
EXPOSE 8000

# Mit gunicorn starten (produktionstauglicher als app.run)
# 2 Worker + Timeout 60s (OCR kann etwas dauern)
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 60 app:app
