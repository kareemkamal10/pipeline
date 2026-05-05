#!/bin/bash
# setup.sh — إعداد بيئة Lightning.ai وGCP
# يثبت المكتبات المطلوبة ويُعدّ Google Cloud
#
# الاستخدام:
#   bash vertex/setup.sh

set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()      { echo -e "${GREEN}▶ $1${NC}"; }
log_warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
log_err()  { echo -e "${RED}  ✗ $1${NC}"; exit 1; }
ok()       { echo -e "${GREEN}  ✔ $1${NC}"; }

# ── التحقق من الملفات المطلوبة ────────────────────────────
[ ! -f "secrets/CREDENTIALS.json" ]   && log_err "secrets/CREDENTIALS.json غير موجود"
[ ! -f "vertex/config_vertex.yaml" ]  && log_err "vertex/config_vertex.yaml غير موجود"
[ ! -f "config.yaml" ]                && log_err "config.yaml غير موجود"

# ── قراءة الإعدادات من config_vertex.yaml ─────────────────
_vcfg() { python3 -c "import yaml; cfg=yaml.safe_load(open('vertex/config_vertex.yaml')); print(cfg$1)"; }
_cfg()  { python3 -c "import yaml; cfg=yaml.safe_load(open('config.yaml')); print(cfg$1)"; }

REGION=$(_vcfg "['gcp']['region']")
ZONE=$(_vcfg "['gcp']['zone']")
REPO_NAME=$(_vcfg "['docker']['repo_name']")
IMAGE_NAME=$(_vcfg "['docker']['image_name']")
BUCKET_NAME_CFG=$(_vcfg "['storage']['bucket_name']")
SESSION_NAME=$(_cfg "['session_name']")

PROJECT_ID=$(python3 -c "import json; print(json.load(open('secrets/CREDENTIALS.json'))['project_id'])")
BUCKET_NAME="${BUCKET_NAME_CFG:-${PROJECT_ID}-pipeline-data}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  History Lab Pipeline — إعداد GCP"
echo "  Project  : ${PROJECT_ID}"
echo "  Region   : ${REGION}"
echo "  Bucket   : gs://${BUCKET_NAME}"
echo "  Session  : ${SESSION_NAME}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── الخطوة 1: تثبيت gcloud ────────────────────────────────
log "الخطوة 1/5 — التحقق من gcloud CLI..."
if ! command -v gcloud &>/dev/null; then
    log_warn "gcloud غير مثبت — جارٍ التثبيت..."
    curl -sSL https://sdk.cloud.google.com > /tmp/install_gcloud.sh
    bash /tmp/install_gcloud.sh --disable-prompts --install-dir="${HOME}/google-cloud-sdk"
    export PATH="${HOME}/google-cloud-sdk/bin:${PATH}"
    echo 'export PATH="${HOME}/google-cloud-sdk/bin:${PATH}"' >> ~/.bashrc
    ok "تم تثبيت gcloud"
else
    ok "gcloud: $(gcloud version --format='value(Google Cloud SDK)' 2>/dev/null | head -1)"
fi

# ── الخطوة 2: تثبيت Docker ────────────────────────────────
log "الخطوة 2/5 — التحقق من Docker..."
if ! command -v docker &>/dev/null; then
    log_warn "Docker غير مثبت — جارٍ التثبيت..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    ok "تم تثبيت Docker — شغّل: newgrp docker"
else
    ok "Docker: $(docker --version)"
fi

# ── الخطوة 3: تفعيل GCP ───────────────────────────────────
log "الخطوة 3/5 — تفعيل GCP..."
export GOOGLE_APPLICATION_CREDENTIALS="secrets/CREDENTIALS.json"
gcloud auth activate-service-account --key-file="secrets/CREDENTIALS.json" --quiet
gcloud config set project "${PROJECT_ID}" --quiet
ok "Service Account مفعّل"

log_warn "تفعيل الـ APIs..."
gcloud services enable \
    compute.googleapis.com \
    artifactregistry.googleapis.com \
    storage.googleapis.com \
    aiplatform.googleapis.com \
    --quiet
ok "APIs مفعّلة (Compute + Artifact Registry + Storage + Vertex AI)"

# ── الخطوة 4: GCS Bucket + المفاتيح ──────────────────────
log "الخطوة 4/5 — إعداد GCS Bucket..."
if gsutil ls "gs://${BUCKET_NAME}" &>/dev/null; then
    log_warn "Bucket موجود: gs://${BUCKET_NAME}"
else
    gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${BUCKET_NAME}"
    ok "تم إنشاء: gs://${BUCKET_NAME}"
fi

gsutil cp "secrets/CREDENTIALS.json" "gs://${BUCKET_NAME}/secrets/CREDENTIALS.json"
ok "CREDENTIALS.json مرفوع"

if [ -f "secrets/kaggle.json" ]; then
    gsutil cp "secrets/kaggle.json" "gs://${BUCKET_NAME}/secrets/kaggle.json"
    ok "kaggle.json مرفوع"
else
    log_warn "secrets/kaggle.json غير موجود"
fi

# ── الخطوة 5: Docker Image ────────────────────────────────
log "الخطوة 5/5 — بناء Docker Image..."
if ! gcloud artifacts repositories describe "${REPO_NAME}" \
    --location="${REGION}" --quiet &>/dev/null; then
    gcloud artifacts repositories create "${REPO_NAME}" \
        --repository-format=docker --location="${REGION}" --quiet
    ok "تم إنشاء Artifact Registry"
fi

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
log_warn "جارٍ البناء (~10 دقائق)..."
docker build -f vertex/Dockerfile -t "${IMAGE_URI}" . --platform linux/amd64
log_warn "جارٍ الرفع..."
docker push "${IMAGE_URI}"
ok "Image: ${IMAGE_URI}"

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
echo -e "${GREEN}  ✔ الإعداد اكتمل! الخطوة التالية:${NC}"
echo "  bash vertex/run.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
