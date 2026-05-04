#!/bin/bash
# entrypoint.sh — يعمل داخل الـ container على GCP
# ينسّق بين GCS والـ pipeline ويحفظ النتائج

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()      { echo -e "${GREEN}▶ $1${NC}"; }
log_warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
log_err()  { echo -e "${RED}✗ $1${NC}"; }

# ── متغيرات البيئة المطلوبة ───────────────────────────────
: "${GCS_BUCKET:?يجب تحديد GCS_BUCKET}"
: "${SESSION_NAME:?يجب تحديد SESSION_NAME}"

PIPELINE_DIR="/app"
DATA_DIR="${PIPELINE_DIR}/data"
SECRETS_DIR="${PIPELINE_DIR}/secrets"

log "بدء تشغيل Pipeline — الجلسة: ${SESSION_NAME}"
log "GCS Bucket: gs://${GCS_BUCKET}"

# ── إعداد مجلد secrets من GCS ────────────────────────────
log "تحميل المفاتيح من GCS..."
mkdir -p "${SECRETS_DIR}"

gsutil cp "gs://${GCS_BUCKET}/secrets/kaggle.json"      "${SECRETS_DIR}/kaggle.json"      2>/dev/null \
    && log "  ✔ kaggle.json" \
    || log_warn "  kaggle.json غير موجود في GCS — سيتم تخطي الرفع"

gsutil cp "gs://${GCS_BUCKET}/secrets/CREDENTIALS.json" "${SECRETS_DIR}/CREDENTIALS.json" 2>/dev/null \
    && log "  ✔ CREDENTIALS.json" \
    || log_warn "  CREDENTIALS.json غير موجود في GCS — سيتم تخطي التشكيل"

# ── تحميل البيانات الموجودة مسبقاً من GCS (للاستئناف) ────
log "فحص بيانات موجودة مسبقاً في GCS..."
if gsutil ls "gs://${GCS_BUCKET}/${SESSION_NAME}/data/" &>/dev/null; then
    log "  استئناف — تحميل البيانات السابقة..."
    mkdir -p "${DATA_DIR}"
    gsutil -m rsync -r \
        "gs://${GCS_BUCKET}/${SESSION_NAME}/data/" \
        "${DATA_DIR}/" \
        2>/dev/null || true
    log "  ✔ تم استئناف البيانات"
else
    log "  بدء جديد — لا توجد بيانات سابقة"
fi

# ── تشغيل الـ Pipeline ────────────────────────────────────
cd "${PIPELINE_DIR}"

# تحديث session_name في config.yaml
python3 -c "
import yaml, sys
with open('config.yaml', 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
cfg['session_name'] = '${SESSION_NAME}'
with open('config.yaml', 'w', encoding='utf-8') as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
print('✔ session_name محدّث:', '${SESSION_NAME}')
"

log "تشغيل Pipeline..."
bash run_pipeline.sh

# ── رفع النتائج إلى GCS ───────────────────────────────────
log "رفع النتائج إلى GCS..."
gsutil -m rsync -r \
    "${DATA_DIR}/" \
    "gs://${GCS_BUCKET}/${SESSION_NAME}/data/"

log "✔ اكتمل كل شيء — النتائج في:"
log "  gs://${GCS_BUCKET}/${SESSION_NAME}/data/"
