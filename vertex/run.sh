#!/bin/bash
# run.sh — تشغيل Pipeline على GCE VM
# يقرأ إعدادات الـ GPU والـ VM من config_vertex.yaml
#
# الاستخدام:
#   bash vertex/run.sh
#   bash vertex/run.sh --rebuild

set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()      { echo -e "${GREEN}▶ $1${NC}"; }
log_warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
ok()       { echo -e "${GREEN}  ✔ $1${NC}"; }

[ ! -f "vertex/.env" ] && echo "✗ شغّل setup.sh أولاً: bash vertex/setup.sh" && exit 1
source vertex/.env

# ── قراءة إعدادات الـ VM من config_vertex.yaml ────────────
_vcfg() { python3 -c "import yaml; cfg=yaml.safe_load(open('vertex/config_vertex.yaml')); print(cfg$1)"; }

GPU_TYPE=$(_vcfg "['vm']['gpu_type']")
GPU_COUNT=$(_vcfg "['vm']['gpu_count']")
MACHINE_TYPE=$(_vcfg "['vm']['machine_type']")
DISK_SIZE_GB=$(_vcfg "['vm']['disk_size_gb']")

VM_NAME="pipeline-$(date +%Y%m%d-%H%M%S)"
REBUILD=false
for arg in "$@"; do
    case $arg in --rebuild) REBUILD=true ;; esac
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  تشغيل Pipeline على GCP"
echo "  VM       : ${VM_NAME}"
echo "  GPU      : ${GPU_TYPE} × ${GPU_COUNT}"
echo "  Machine  : ${MACHINE_TYPE}"
echo "  Disk     : ${DISK_SIZE_GB}GB"
echo "  Session  : ${SESSION_NAME}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$REBUILD" = true ]; then
    log "إعادة بناء Docker Image..."
    docker build -f vertex/Dockerfile -t "${IMAGE_URI}" . --platform linux/amd64
    docker push "${IMAGE_URI}"
    ok "Image محدّث"
fi

export GOOGLE_APPLICATION_CREDENTIALS="secrets/CREDENTIALS.json"
gcloud auth activate-service-account --key-file="secrets/CREDENTIALS.json" --quiet
gcloud config set project "${PROJECT_ID}" --quiet

log "إنشاء VM..."
gcloud compute instances create "${VM_NAME}" \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    --machine-type="${MACHINE_TYPE}" \
    --accelerator="type=${GPU_TYPE},count=${GPU_COUNT}" \
    --maintenance-policy=TERMINATE \
    --boot-disk-size="${DISK_SIZE_GB}GB" \
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
docker run --rm --gpus all \
    -e GCS_BUCKET=${BUCKET_NAME} \
    -e SESSION_NAME=${SESSION_NAME} \
    ${IMAGE_URI}
shutdown -h now" \
    --quiet

ok "VM مُنشأ: ${VM_NAME}"
echo "${VM_NAME} ${ZONE}" >> vertex/.vms_created

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}  ✔ Pipeline يعمل على GCP${NC}"
echo ""
echo "  متابعة السجلات:"
echo "  gcloud compute ssh ${VM_NAME} --zone=${ZONE} -- \\"
echo "    'sudo journalctl -f -u google-startup-scripts'"
echo ""
echo "  Console:"
echo "  https://console.cloud.google.com/compute/instances?project=${PROJECT_ID}"
echo ""
echo "  النتائج بعد الانتهاء:"
echo "  gs://${BUCKET_NAME}/${SESSION_NAME}/data/"
echo ""
echo "  الـ VM يوقف نفسه تلقائياً بعد الانتهاء."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
