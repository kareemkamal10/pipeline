#!/bin/bash
# run_pipeline.sh — تشغيل الـ pipeline كاملاً بشكل متسلسل
#
# الترتيب:
#   1. تحميل الصوت من YouTube          (CPU)
#   2. معالجة الصوت (Demucs + Whisper) (GPU)
#   3. تشكيل النصوص بـ Gemini          (CPU — يتحكم فيه config.yaml)
#   4. رفع النتائج إلى Kaggle          (CPU — يتحكم فيه config.yaml)
#
# الاستخدام:
#   bash run_pipeline.sh
#   bash run_pipeline.sh --skip-diacritize
#   bash run_pipeline.sh --skip-upload
#   bash run_pipeline.sh mylinks.csv

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_step()  { echo -e "\n${GREEN}▶ $1${NC}"; }
log_warn()  { echo -e "${YELLOW}  ⚠ $1${NC}"; }

# ── قراءة config.yaml ─────────────────────────────────────────────────────────
_cfg() { python3 -c "import config_loader; print(config_loader.load()$1)" 2>/dev/null; }

DIACRITIZE_AUTO=$(python3 -c "import config_loader; print(config_loader.diacritization().get('auto', False))" 2>/dev/null || echo "False")
UPLOAD_AUTO=$(python3 -c "import config_loader; print(config_loader.upload_config().get('auto', False))" 2>/dev/null || echo "False")
SESSION=$(python3 -c "import config_loader; print(config_loader.session_name())" 2>/dev/null || echo "pipeline")

# ── قراءة الخيارات من سطر الأوامر ──────────────────────────────────────────────
FORCE_SKIP_DIA=false
FORCE_SKIP_UPLOAD=false
PLAYLIST_FILE="playLinks.csv"

for arg in "$@"; do
    case $arg in
        --skip-diacritize) FORCE_SKIP_DIA=true ;;
        --skip-upload)     FORCE_SKIP_UPLOAD=true ;;
        *.csv)             PLAYLIST_FILE=$arg ;;
    esac
done

# ── الترحيب ───────────────────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  History Lab Pipeline"
echo "  الجلسة  : $SESSION"
echo "  التشكيل : $([ "$DIACRITIZE_AUTO" = "True" ] && echo "تلقائي" || echo "يدوي")"
echo "  الرفع   : $([ "$UPLOAD_AUTO" = "True" ] && echo "تلقائي" || echo "يدوي")"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ ! -f "$PLAYLIST_FILE" ]; then
    echo -e "${RED}✗ ملف $PLAYLIST_FILE غير موجود${NC}"
    exit 1
fi

START_TIME=$(date +%s)

# ── المرحلة 1: التحميل ────────────────────────────────────────────────────────
log_step "المرحلة 1/4 — تحميل الصوت من YouTube"
python main.py download "$PLAYLIST_FILE"

# ── المرحلة 2: المعالجة ───────────────────────────────────────────────────────
log_step "المرحلة 2/4 — معالجة الصوت (Demucs + WhisperX)"
python main.py process

# ── المرحلة 3: التشكيل ────────────────────────────────────────────────────────
if [ "$FORCE_SKIP_DIA" = true ]; then
    log_warn "تجاوز التشكيل (--skip-diacritize)"
elif [ "$DIACRITIZE_AUTO" != "True" ]; then
    log_warn "التشكيل معطّل في config.yaml (diacritization.auto: false) — شغّله يدوياً: python diacritize.py"
else
    log_step "المرحلة 3/4 — تشكيل النصوص بـ Gemini"
    CREDS=$(python3 -c "import config_loader; print(config_loader.google_credentials())" 2>/dev/null)
    if [ ! -f "$CREDS" ]; then
        log_warn "$CREDS غير موجود — تجاوز التشكيل"
    else
        python diacritize.py --yes
    fi
fi

# ── المرحلة 4: الرفع ──────────────────────────────────────────────────────────
if [ "$FORCE_SKIP_UPLOAD" = true ]; then
    log_warn "تجاوز الرفع (--skip-upload)"
elif [ "$UPLOAD_AUTO" != "True" ]; then
    log_warn "الرفع معطّل في config.yaml (upload.auto: false) — شغّله يدوياً: python main.py upload"
else
    log_step "المرحلة 4/4 — رفع النتائج إلى Kaggle"
    KAGGLE=$(python3 -c "import config_loader; print(config_loader.kaggle_credentials())" 2>/dev/null)
    if [ ! -f "$KAGGLE" ]; then
        log_warn "$KAGGLE غير موجود — تجاوز الرفع"
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
echo -e "${GREEN}  ✔ اكتمل الـ pipeline! — $SESSION${NC}"
printf "  الوقت المستغرق: %02d:%02d:%02d\n" $HOURS $MINUTES $SECONDS
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
