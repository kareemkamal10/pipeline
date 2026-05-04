#!/bin/bash
# cleanup.sh — حذف الـ VMs بعد الانتهاء لتوفير التكلفة
#
# الاستخدام:
#   bash vertex/cleanup.sh

set -e

if [ ! -f "vertex/.env" ]; then
    echo "✗ vertex/.env غير موجود"
    exit 1
fi

source vertex/.env

export GOOGLE_APPLICATION_CREDENTIALS="secrets/CREDENTIALS.json"
gcloud auth activate-service-account --key-file="secrets/CREDENTIALS.json" --quiet
gcloud config set project "${PROJECT_ID}" --quiet

if [ ! -f "vertex/.vms_created" ] || [ ! -s "vertex/.vms_created" ]; then
    echo "✔ لا توجد VMs مسجّلة للحذف"
    exit 0
fi

echo "▶ حذف الـ VMs..."
while IFS=" " read -r vm_name vm_zone; do
    if gcloud compute instances describe "${vm_name}" --zone="${vm_zone}" --quiet &>/dev/null; then
        gcloud compute instances delete "${vm_name}" --zone="${vm_zone}" --quiet
        echo "  ✔ تم حذف: ${vm_name}"
    else
        echo "  ↩ غير موجود (ربما حُذف مسبقاً): ${vm_name}"
    fi
done < vertex/.vms_created

rm -f vertex/.vms_created
echo "✔ اكتمل الحذف"
