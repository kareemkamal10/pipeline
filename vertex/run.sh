#!/bin/bash
# run.sh — تشغيل الـ Pipeline على GCE VM بـ L4 GPU
#
# الاستخدام:
#   bash vertex/run.sh
#   bash vertex/run.sh --rebuild     # إعادة بناء Docker Image

set -e

if [ ! -f "vertex/.env" ]; then
    echo "✗ ملف vertex/.env غير موجود — شغّل setup.sh أولاً:"
    echo "  bash vertex/setup.sh"
    exit 1
fi

source vertex/.env

VM_NAME="pipeline-$(date +%Y%m%d-%H%M%S)"
MACHINE_TYPE="g2-standard-8"
GPU_TYPE="nvidia-l4"
DISK_SIZE="100GB"
ZONE="${REGION}-a"
REBUILD=false

for arg in "$@"; do
    case $arg in
        --rebuild) REBUILD=true ;;
    esac
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  تشغيل Pipeline على GCP"
echo "  VM      : ${VM_NAME}"
echo "  GPU     : ${GPU_TYPE} (L4 — 24GB VRAM)"
echo "  Session : ${SESSION_NAME}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$REBUILD" = true ]; then
    echo "▶ إعادة بناء Docker Image..."
    docker build -f vertex/Dockerfile -t "${IMAGE_URI}" . --platform linux/amd64
    docker push "${IMAGE_URI}"
    echo "  ✔ تم تحديث Image"
fi

export GOOGLE_APPLICATION_CREDENTIALS="secrets/CREDENTIALS.json"
gcloud auth activate-service-account --key-file="secrets/CREDENTIALS.json" --quiet
gcloud config set project "${PROJECT_ID}" --quiet

echo "▶ إنشاء VM..."

gcloud compute instances create "${VM_NAME}" \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    --machine-type="${MACHINE_TYPE}" \
    --accelerator="type=${GPU_TYPE},count=1" \
    --maintenance-policy=TERMINATE \
    --boot-disk-size="${DISK_SIZE}" \
    --boot-disk-type=pd-ssd \
    --image-family=debian-12 \
    --image-project=debian-cloud \
    --scopes=cloud-platform \
    --metadata=startup-script="#! /bin/bash
set -e
curl -fsSL https://get.docker.com | sh
distribution=\$(. /etc/os-release; echo \$ID\$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/\$distribution/libnvidia-container.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update && apt-get install -y nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet
docker run --rm --gpus all -e GCS_BUCKET=${BUCKET_NAME} -e SESSION_NAME=${SESSION_NAME} ${IMAGE_URI}
shutdown -h now" \
    --quiet

echo "  ✔ VM مُنشأ: ${VM_NAME}"
echo "${VM_NAME} ${ZONE}" >> vertex/.vms_created

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✔ Pipeline يعمل الآن على GCP"
echo ""
echo "  متابعة السجلات:"
echo "  gcloud compute ssh ${VM_NAME} --zone=${ZONE} -- 'sudo journalctl -f -u google-startup-scripts'"
echo ""
echo "  Console:"
echo "  https://console.cloud.google.com/compute/instances?project=${PROJECT_ID}"
echo ""
echo "  النتائج:"
echo "  gs://${BUCKET_NAME}/${SESSION_NAME}/data/"
echo ""
echo "  الـ VM يوقف نفسه تلقائياً بعد الانتهاء."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
