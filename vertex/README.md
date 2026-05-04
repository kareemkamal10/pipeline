# تشغيل Pipeline على Google Cloud من Lightning.ai

---

## المتطلبات الأولية

على Lightning.ai لا تحتاج تثبيت أي شيء يدوياً —
`setup.sh` يثبت كل شيء تلقائياً:
- **gcloud CLI** — للتواصل مع Google Cloud
- **Docker** — لبناء ورفع الـ container

الشيء الوحيد المطلوب منك مسبقاً:
- ملف `secrets/CREDENTIALS.json` — Service Account من Google Cloud

---

## إعداد CREDENTIALS.json (مرة واحدة)

اذهب إلى Google Cloud Console:

**1.** https://console.cloud.google.com/iam-admin/serviceaccounts

**2.** اضغط **Create Service Account**
- الاسم: `pipeline-runner`
- اضغط **Create and Continue**

**3.** أضف هذه الصلاحيات:
- `Storage Admin`
- `Artifact Registry Administrator`
- `Compute Admin`

**4.** اضغط **Done** ثم على الـ Service Account → **Keys** → **Add Key** → **JSON**

**5.** ارفع الملف المحمّل إلى Lightning.ai في:
```
secrets/CREDENTIALS.json
```

---

## التشغيل من Lightning.ai

### الخطوة 1 — إعداد GCP (مرة واحدة)

```bash
cd ~/pipeline
bash vertex/setup.sh
```

يقوم تلقائياً بـ:
- تثبيت `gcloud CLI` إذا لم يكن موجوداً
- تثبيت `Docker` إذا لم يكن موجوداً
- تفعيل الـ APIs على GCP
- إنشاء GCS Bucket لحفظ البيانات
- رفع المفاتيح إلى GCS بأمان
- بناء Docker Image ورفعه (~10 دقائق)

---

### الخطوة 2 — تشغيل Pipeline

```bash
bash vertex/run.sh
```

يقوم بـ:
- إنشاء GCE VM بـ **L4 GPU (24GB VRAM)** تلقائياً
- تشغيل Pipeline كامل داخل الـ VM:
  - تحميل الصوت من YouTube
  - معالجة بـ Demucs + WhisperX
  - تشكيل النصوص بـ Gemini (إذا مفعّل)
  - رفع النتائج على Kaggle (إذا مفعّل)
- حفظ كل النتائج في GCS
- **إيقاف الـ VM تلقائياً** بعد الانتهاء

```bash
# إعادة بناء الـ Image قبل التشغيل (بعد أي تعديل في الكود)
bash vertex/run.sh --rebuild
```

---

### متابعة التشغيل

بعد تشغيل `run.sh` الـ VM يعمل في الخلفية.

**لمتابعة السجلات مباشرة:**
```bash
# استبدل VM_NAME بالاسم الذي ظهر عند التشغيل
gcloud compute ssh VM_NAME --zone=us-central1-a -- \
    'sudo journalctl -f -u google-startup-scripts'
```

**من Console:**
https://console.cloud.google.com/compute/instances

---

### تحميل النتائج بعد الانتهاء

```bash
source vertex/.env

# تحميل كل البيانات
gsutil -m rsync -r \
    "gs://${BUCKET_NAME}/${SESSION_NAME}/data/" \
    "data/"

# تحميل metadata فقط
gsutil cp \
    "gs://${BUCKET_NAME}/${SESSION_NAME}/data/metadata/tts_metadata.json" \
    "data/metadata/"
```

---

### تنظيف الموارد (مهم لتوفير التكلفة)

```bash
bash vertex/cleanup.sh
```

---

## التكلفة التقريبية

| العملية | الوقت | التكلفة |
|---------|-------|---------|
| `setup.sh` (بناء Image) | ~10 دقائق | ~$0.10 |
| `run.sh` (L4 GPU) | ~3-5 ساعات | ~$2-4 |
| تخزين GCS | مستمر | ~$0.02/GB/شهر |
| **إجمالي الجلسة** | | **~$3-5** |

مع رصيد $271 → أكثر من **50 جلسة** كاملة.

---

## هيكل الملفات

```
vertex/
├── Dockerfile        ← صورة Docker للـ Pipeline
├── entrypoint.sh     ← يعمل داخل الـ container على GCP
├── setup.sh          ← إعداد GCP + تثبيت gcloud وDocker
├── run.sh            ← إنشاء VM وتشغيل Pipeline
├── cleanup.sh        ← حذف الـ VMs بعد الانتهاء
├── README.md         ← هذا الملف
├── .env              ← إعدادات محفوظة (يُنشأ تلقائياً)
└── .vms_created      ← سجل الـ VMs (يُنشأ تلقائياً)
```

---

## استكشاف الأخطاء

**خطأ: Permission denied على Docker**
```bash
newgrp docker
# ثم أعد تشغيل setup.sh
```

**خطأ: Quota exceeded**
- اذهب إلى: https://console.cloud.google.com/iam-admin/quotas
- ابحث عن `NVIDIA_L4_GPUS` في `Compute Engine API`
- اطلب زيادة إلى 1

**خطأ: Image build failed**
```bash
# أعد البناء مع إظهار التفاصيل
docker build -f vertex/Dockerfile . --platform linux/amd64 --no-cache
```
