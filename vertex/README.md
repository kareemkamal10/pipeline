# تشغيل Pipeline على Google Cloud

## المتطلبات على جهازك

```bash
# تثبيت gcloud CLI
curl https://sdk.cloud.google.com | bash
gcloud init

# تثبيت Docker
# https://docs.docker.com/get-docker/
```

---

## الإعداد من Console (مرة واحدة)

### 1. تفعيل الـ APIs
اذهب إلى: https://console.cloud.google.com/apis/library

فعّل هذه الـ APIs:
- **Compute Engine API**
- **Artifact Registry API**
- **Cloud Storage API**

### 2. طلب GPU Quota (مهم — قد يستغرق 24-48 ساعة)

اذهب إلى: https://console.cloud.google.com/iam-admin/quotas

- ابحث عن: `NVIDIA_L4_GPUS`
- Region: `us-central1`
- اضغط **Edit Quotas** → اطلب **1**
- اكتب سبباً: "Running AI audio processing pipeline"

### 3. إنشاء Service Account (اختياري — إذا لم يكن CREDENTIALS.json جاهزاً)

اذهب إلى: https://console.cloud.google.com/iam-admin/serviceaccounts

- **Create Service Account**
- الاسم: `pipeline-runner`
- الصلاحيات:
  - `Storage Admin`
  - `Artifact Registry Admin`
  - `Compute Admin`
- **Create Key** → JSON → احفظه كـ `secrets/CREDENTIALS.json`

---

## التشغيل (بعد الموافقة على الـ Quota)

### الخطوة 1 — إعداد GCP (مرة واحدة)
```bash
bash vertex/setup.sh
```

يقوم بـ:
- تفعيل الـ APIs
- إنشاء GCS Bucket لحفظ البيانات
- رفع المفاتيح إلى GCS بأمان
- بناء Docker Image ورفعه إلى Artifact Registry

### الخطوة 2 — تشغيل Pipeline
```bash
bash vertex/run.sh
```

يقوم بـ:
- إنشاء VM بـ L4 GPU تلقائياً
- تشغيل Pipeline كامل (تحميل + معالجة + تشكيل + رفع)
- حفظ النتائج في GCS
- إيقاف الـ VM تلقائياً بعد الانتهاء

### خيارات إضافية
```bash
bash vertex/run.sh --rebuild    # إعادة بناء Docker Image قبل التشغيل
```

---

## متابعة التشغيل

**السجلات المباشرة:**
```bash
# استبدل VM_NAME بالاسم الذي ظهر عند التشغيل
gcloud compute ssh VM_NAME --zone=us-central1-a -- \
    'sudo journalctl -f -u google-startup-scripts'
```

**من Console:**
https://console.cloud.google.com/compute/instances

---

## تحميل النتائج بعد الانتهاء

```bash
source vertex/.env

# تحميل كل البيانات
gsutil -m rsync -r \
    "gs://${BUCKET_NAME}/${SESSION_NAME}/data/" \
    "data/"

# أو تحميل metadata فقط
gsutil cp \
    "gs://${BUCKET_NAME}/${SESSION_NAME}/data/metadata/tts_metadata.json" \
    "data/metadata/"
```

---

## تنظيف الموارد (مهم — لتوفير التكلفة)

```bash
bash vertex/cleanup.sh
```

---

## التكلفة التقريبية

| المرحلة | الوقت المتوقع | التكلفة |
|---------|--------------|---------|
| بناء Image | ~10 دقائق | ~$0.10 |
| تشغيل Pipeline (L4) | ~3-5 ساعات | ~$2-4 |
| تخزين GCS | حسب الحجم | ~$0.02/GB/شهر |
| **الإجمالي للجلسة** | | **~$3-5** |

مع رصيد $271 → أكثر من 50 جلسة كاملة.

---

## هيكل الملفات

```
vertex/
├── Dockerfile       ← صورة Docker للـ Pipeline
├── entrypoint.sh    ← يعمل داخل الـ container
├── setup.sh         ← إعداد GCP (مرة واحدة)
├── run.sh           ← تشغيل Pipeline
├── cleanup.sh       ← حذف الـ VMs
├── .env             ← إعدادات محفوظة (يُنشأ تلقائياً)
└── .vms_created     ← سجل الـ VMs (يُنشأ تلقائياً)
```
