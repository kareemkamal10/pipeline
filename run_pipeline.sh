#!/bin/bash
# run_pipeline.sh — تشغيل الـ pipeline كاملاً بشكل متسلسل
#
# الترتيب:
#   1. تحميل الصوت من YouTube          (CPU)
#   2. معالجة الصوت (Demucs + Whisper) (GPU)
#   3. تشكيل النصوص بـ Gemini          (CPU — اختياري)
#   4. رفع النتائج إلى Kaggle          (CPU)
#
# الاستخدام:
#   bash run_pipeline.sh                  # كامل مع التشكيل
#   bash run_pipeline.sh --skip-diacritize  # بدون خطوة التشكيل
#   bash run_pipeline.sh --skip-upload      # بدون رفع Kaggle

set -e   # توقف فوراً عند أي خطأ

# ── ألوان للطباعة ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_step()  { echo -e "\n${GREEN}▶ $1${NC}"; }
log_warn()  { echo -e "${YELLOW}  ⚠ $1${NC}"; }
log_error() { echo -e "${RED}  ✗ $1${NC}"; }

# ── قراءة الخيارات ────────────────────────────────────────────────────────────
SKIP_DIACRITIZE=false
SKIP_UPLOAD=false
PLAYLIST_FILE="playLinks.csv"

for arg in "$@"; do
    case $arg in
        --skip-diacritize) SKIP_DIACRITIZE=true ;;
        --skip-upload)     SKIP_UPLOAD=true ;;
        *.csv)             PLAYLIST_FILE=$arg ;;
    esac
done

# ── التحقق من الملفات الأساسية ────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  History Lab Pipeline"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ ! -f "$PLAYLIST_FILE" ]; then
    log_error "ملف $PLAYLIST_FILE غير موجود"
    exit 1
fi

if [ ! -f "config.yaml" ]; then
    log_error "ملف config.yaml غير موجود"
    exit 1
fi

START_TIME=$(date +%s)

# ── المرحلة 1: التحميل ────────────────────────────────────────────────────────
log_step "المرحلة 1/4 — تحميل الصوت من YouTube"
python main.py download "$PLAYLIST_FILE"

# ── المرحلة 2: المعالجة ───────────────────────────────────────────────────────
log_step "المرحلة 2/4 — معالجة الصوت (Demucs + WhisperX)"
python main.py process

# ── المرحلة 3: التشكيل (اختياري) ─────────────────────────────────────────────
if [ "$SKIP_DIACRITIZE" = true ]; then
    log_warn "تجاوز خطوة التشكيل (--skip-diacritize)"
else
    log_step "المرحلة 3/4 — تشكيل النصوص بـ Gemini (اختياري — لضمان الدقة)"

    if [ ! -f "secrets/CREDENTIALS.json" ]; then
        log_warn "secrets/CREDENTIALS.json غير موجود — تجاوز التشكيل"
    else
        python diacritize.py --yes
    fi
fi

# ── المرحلة 4: الرفع ──────────────────────────────────────────────────────────
if [ "$SKIP_UPLOAD" = true ]; then
    log_warn "تجاوز الرفع (--skip-upload)"
else
    log_step "المرحلة 4/4 — رفع النتائج إلى Kaggle"

    if [ ! -f "secrets/kaggle.json" ]; then
        log_warn "secrets/kaggle.json غير موجود — تجاوز الرفع"
    else
        python main.py upload
    fi
fi

# ── الملخص ────────────────────────────────────────────────────────────────────
END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
HOURS=$(( ELAPSED / 3600 ))
MINUTES=$(( (ELAPSED % 3600) / 60 ))
SECONDS=$(( ELAPSED % 60 ))

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}  ✔ اكتمل الـ pipeline!${NC}"
printf "  الوقت المستغرق: %02d:%02d:%02d\n" $HOURS $MINUTES $SECONDS
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
