#!/bin/bash
# setup.sh — إعداد GCP مرة واحدة
# يفعّل الـ APIs، ينشئ GCS Bucket، يبني Docker Image ويرفعه
#
# الاستخدام:
#   bash vertex/setup.sh

set -e

# ── قراءة الإعدادات ───────────────────────────────────────
CREDENTIALS="secrets/CREDENTIALS.json"

if [ ! -f "$CREDENTIALS" ]; then
    echo "✗ ملف $CREDENTIALS غير موجود"
    exit 1
fi

PROJECT_ID=$(python3 -c "import json; print(json.load(open('$CREDENTIALS'))['project_id'])")
REGION="us-central1"
REPO_NAME="pipeline-repo"
IMAGE_NAME="history-lab-pipeline"
SESSION_NAME=$(python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))['session_name'])")
BUCKET_NAME="${PROJECT_ID}-pipeline-data"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  إعداد GCP — History Lab Pipeline"
echo "  Project : ${PROJECT_ID}"
echo "  Region  : ${REGION}"
echo "  Bucket  : gs://${BUCKET_NAME}"
echo "  Image   : ${IMAGE_NAME}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── تفعيل الـ credentials ─────────────────────────────────
export GOOGLE_APPLICATION_CREDENTIALS="${CREDENTIALS}"
gcloud auth activate-service-account --key-file="${CREDENTIALS}" --quiet
gcloud config set project "${PROJECT_ID}" --quiet

# ── تفعيل الـ APIs ────────────────────────────────────────
echo "▶ تفعيل الـ APIs..."
gcloud services enable \
    compute.googleapis.com \
    artifactregistry.googleapis.com \
    storage.googleapis.com \
    --quiet
echo "  ✔ APIs مفعّلة"

# ── إنشاء GCS Bucket ──────────────────────────────────────
echo "▶ إنشاء GCS Bucket..."
if gsutil ls "gs://${BUCKET_NAME}" &>/dev/null; then
    echo "  ↩ Bucket موجود مسبقاً: gs://${BUCKET_NAME}"
else
    gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${BUCKET_NAME}"
    echo "  ✔ تم إنشاء: gs://${BUCKET_NAME}"
fi

# ── رفع المفاتيح إلى GCS ──────────────────────────────────
echo "▶ رفع المفاتيح إلى GCS..."
gsutil cp secrets/CREDENTIALS.json "gs://${BUCKET_NAME}/secrets/CREDENTIALS.json"
echo "  ✔ CREDENTIALS.json"

if [ -f "secrets/kaggle.json" ]; then
    gsutil cp secrets/kaggle.json "gs://${BUCKET_NAME}/secrets/kaggle.json"
    echo "  ✔ kaggle.json"
else
    echo "  ⚠ kaggle.json غير موجود — سيتم تخطي الرفع على Kaggle"
fi

# ── إنشاء Artifact Registry ───────────────────────────────
echo "▶ إعداد Artifact Registry..."
if gcloud artifacts repositories describe "${REPO_NAME}" \
    --location="${REGION}" --quiet &>/dev/null; then
    echo "  ↩ Repository موجود مسبقاً"
else
    gcloud artifacts repositories create "${REPO_NAME}" \
        --repository-format=docker \
        --location="${REGION}" \
        --quiet
    echo "  ✔ تم إنشاء repository"
fi

# ── بناء ورفع Docker Image ────────────────────────────────
echo "▶ بناء Docker Image..."
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

docker build \
    -f vertex/Dockerfile \
    -t "${IMAGE_URI}" \
    . \
    --platform linux/amd64

echo "▶ رفع Image إلى Artifact Registry..."
docker push "${IMAGE_URI}"
echo "  ✔ Image: ${IMAGE_URI}"

# ── حفظ الإعدادات في ملف مؤقت ───────────────────────────
cat > vertex/.env << ENVEOF
PROJECT_ID=${PROJECT_ID}
REGION=${REGION}
BUCKET_NAME=${BUCKET_NAME}
IMAGE_URI=${IMAGE_URI}
SESSION_NAME=${SESSION_NAME}
ENVEOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✔ الإعداد اكتمل!"
echo ""
echo "  الخطوة التالية:"
echo "  bash vertex/run.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
