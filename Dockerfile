# AeroCombat TEKNOFEST Savasan IHA Dockerfile
# Python 3.11 Slim Image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Sistem bağımlılıkları (OpenCV ve GUI kütüphaneleri için)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Bağımlılıkları yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Proje dosyalarını kopyala
COPY . .

# Portlar: 8000 (Mock Hakem Sunucusu), 8080 (Web GCS Görev Paneli)
EXPOSE 8000 8080

# Varsayılan çalıştırma komutu (Headless mod)
CMD ["python", "main.py", "--no-gui"]
