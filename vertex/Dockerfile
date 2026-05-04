FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime

# ── متغيرات البناء ────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIPELINE_DIR=/app

# ── أدوات النظام ──────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# ── مجلد العمل ───────────────────────────────────────────
WORKDIR ${PIPELINE_DIR}

# ── نسخ ملفات المشروع ─────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── تثبيت أدوات إضافية ───────────────────────────────────
RUN pip install --no-cache-dir \
    yt-dlp \
    google-cloud-storage \
    kaggle

# ── نسخ كود المشروع ───────────────────────────────────────
COPY *.py .
COPY *.yaml .
COPY *.csv .
COPY *.sh .

# ── نقطة الدخول ──────────────────────────────────────────
COPY vertex/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh /app/*.sh

ENTRYPOINT ["/entrypoint.sh"]
