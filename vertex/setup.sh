#!/bin/bash
# setup.sh — إعداد بيئة Lightning.ai وGCP
# يثبت المكتبات المطلوبة ويُعدّ Google Cloud
#
# الاستخدام:
#   bash vertex/setup.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()      { echo -e "${GREEN}▶ $1${NC}"; }
log_warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
log_err()  { echo -e "${RED}  ✗ $1${NC}"; exit 1; }
ok()       { echo -e "${GREEN}  ✔ $1${NC}"; }

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  History Lab Pipeline — إعداد GCP من Lightning.ai"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── التحقق من CREDENTIALS.json ────────────────────────────
CREDENTIALS="secrets/CREDENTIALS.json"
if [ ! -f "$CREDENTIALS" ]; then
    log_err "ملف $CREDENTIALS غير موجود — ضعه في secrets/ أولاً"
fi

PROJECT_ID=$(python3 -c "import json; print(json.load(open('$CREDENTIALS'))['project_id'])")
REGION="us-central1"
ZONE="${REGION}-a"
REPO_NAME="pipeline-repo"
IMAGE_NAME="history-lab-pipeline"
BUCKET_NAME="${PROJECT_ID}-pipeline-data"
SESSION_NAME=$(python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))['session_name'])")
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"

echo ""
log "الإعدادات:"
echo "  Project  : ${PROJECT_ID}"
echo "  Region   : ${REGION}"
echo "  Bucket   : gs://${BUCKET_NAME}"
echo "  Session  : ${SESSION_NAME}"
echo ""

# ════════════════════════════════════════════════════════════
# الخطوة 1: تثبيت gcloud CLI
# ════════════════════════════════════════════════════════════
log "الخطوة 1/5 — التحقق من gcloud CLI..."

if ! command -v gcloud &>/dev/null; then
    log_warn "gcloud غير مثبت — جارٍ التثبيت..."

    # تثبيت gcloud على Linux
    curl -sSL https://sdk.cloud.google.com > /tmp/install_gcloud.sh
    bash /tmp/install_gcloud.sh --disable-prompts --install-dir="${HOME}/google-cloud-sdk"

    # إضافة gcloud لـ PATH في الجلسة الحالية
    export PATH="${HOME}/google-cloud-sdk/bin:${PATH}"

    # إضافته بشكل دائم
    echo 'export PATH="${HOME}/google-cloud-sdk/bin:${PATH}"' >> ~/.bashrc

    ok "تم تثبيت gcloud"
else
    ok "gcloud مثبت: $(gcloud version --format='value(Google Cloud SDK)' 2>/dev/null | head -1)"
fi

# ════════════════════════════════════════════════════════════
# الخطوة 2: تثبيت Docker
# ════════════════════════════════════════════════════════════
log "الخطوة 2/5 — التحقق من Docker..."

if ! command -v docker &>/dev/null; then
    log_warn "Docker غير مثبت — جارٍ التثبيت..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    ok "تم تثبيت Docker"
    log_warn "قد تحتاج تشغيل: newgrp docker"
else
    ok "Docker مثبت: $(docker --version)"
fi

# ════════════════════════════════════════════════════════════
# الخطوة 3: تفعيل GCP credentials والـ APIs
# ════════════════════════════════════════════════════════════
log "الخطوة 3/5 — تفعيل GCP..."

export GOOGLE_APPLICATION_CREDENTIALS="${CREDENTIALS}"
gcloud auth activate-service-account --key-file="${CREDENTIALS}" --quiet
gcloud config set project "${PROJECT_ID}" --quiet
ok "تم تفعيل Service Account"

# تفعيل الـ APIs
log_warn "تفعيل الـ APIs (قد يستغرق دقيقة)..."
gcloud services enable \
    compute.googleapis.com \
    artifactregistry.googleapis.com \
    storage.googleapis.com \
    --quiet
ok "APIs مفعّلة"

# ════════════════════════════════════════════════════════════
# الخطوة 4: إنشاء GCS Bucket ورفع المفاتيح
# ════════════════════════════════════════════════════════════
log "الخطوة 4/5 — إعداد GCS Bucket..."

if gsutil ls "gs://${BUCKET_NAME}" &>/dev/null; then
    log_warn "Bucket موجود مسبقاً: gs://${BUCKET_NAME}"
else
    gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${BUCKET_NAME}"
    ok "تم إنشاء: gs://${BUCKET_NAME}"
fi

# رفع المفاتيح بأمان
gsutil cp "${CREDENTIALS}" "gs://${BUCKET_NAME}/secrets/CREDENTIALS.json"
ok "CREDENTIALS.json مرفوع"

if [ -f "secrets/kaggle.json" ]; then
    gsutil cp "secrets/kaggle.json" "gs://${BUCKET_NAME}/secrets/kaggle.json"
    ok "kaggle.json مرفوع"
else
    log_warn "secrets/kaggle.json غير موجود — سيتم تخطي الرفع على Kaggle"
fi

# ════════════════════════════════════════════════════════════
# الخطوة 5: بناء Docker Image ورفعه
# ════════════════════════════════════════════════════════════
log "الخطوة 5/5 — بناء Docker Image..."

# إنشاء Artifact Registry إذا لم يكن موجوداً
if ! gcloud artifacts repositories describe "${REPO_NAME}" \
    --location="${REGION}" --quiet &>/dev/null; then
    gcloud artifacts repositories create "${REPO_NAME}" \
        --repository-format=docker \
        --location="${REGION}" \
        --quiet
    ok "تم إنشاء Artifact Registry"
fi

# تسجيل الدخول لـ Docker
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# بناء Image
log_warn "جارٍ البناء (قد يستغرق 5-10 دقائق)..."
docker build \
    -f vertex/Dockerfile \
    -t "${IMAGE_URI}" \
    . \
    --platform linux/amd64

# رفع Image
log_warn "جارٍ الرفع..."
docker push "${IMAGE_URI}"
ok "Image مرفوع: ${IMAGE_URI}"

# ── حفظ الإعدادات ──────────────────────────────────────────
cat > vertex/.env << ENVEOF
PROJECT_ID=${PROJECT_ID}
REGION=${REGION}
ZONE=${ZONE}
BUCKET_NAME=${BUCKET_NAME}
IMAGE_URI=${IMAGE_URI}
SESSION_NAME=${SESSION_NAME}
ENVEOF
ok "الإعدادات محفوظة في vertex/.env"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}  ✔ الإعداد اكتمل بنجاح!${NC}"
echo ""
echo "  الخطوة التالية:"
echo "  bash vertex/run.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
