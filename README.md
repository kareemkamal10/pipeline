# History Lab Pipeline 🎙️

معالجة تلقائية للمحتوى الصوتي — تحميل، تنقية، تشكيل، ورفع.

---

## هيكل المشروع

```
pipeline/
├── secrets/                  ← مفاتيح API (لا تُرفع على GitHub)
│   ├── CREDENTIALS.json      ← Google Cloud (Vertex AI / Gemini)
│   └── kaggle.json           ← Kaggle API
├── data/                     ← البيانات (لا تُرفع على GitHub)
│   ├── raw_audio/
│   ├── vocals/
│   ├── transcripts/
│   ├── fulltranscripts/
│   └── metadata/
├── main.py
├── processor.py
├── downloader.py
├── uploader.py
├── diacritize.py             ← خدمة التشكيل (مستقلة)
├── run_pipeline.sh           ← تشغيل كامل بأمر واحد
├── playLinks.csv
└── config.yaml
```

---

## الإعداد الأولي (مرة واحدة فقط)

### 1. تثبيت المكتبات

```bash
pip install -r requirements.txt
apt install ffmpeg -y
```

### 2. إعداد المفاتيح

```bash
mkdir -p secrets
```

**Kaggle** — من https://www.kaggle.com/settings → API → Create New Token:
```bash
cp /path/to/kaggle.json secrets/kaggle.json
```

**Google Cloud (Vertex AI)** — من Google Cloud Console:
```bash
cp /path/to/your-key.json secrets/CREDENTIALS.json
```

---

## التشغيل الكامل بأمر واحد

```bash
bash run_pipeline.sh
```

### خيارات التشغيل

```bash
bash run_pipeline.sh                        # كامل (تحميل + معالجة + تشكيل + رفع)
bash run_pipeline.sh --skip-diacritize      # بدون خطوة التشكيل
bash run_pipeline.sh --skip-upload          # بدون رفع إلى Kaggle
bash run_pipeline.sh mylinks.csv            # استخدام ملف CSV مخصص
```

---

## التشغيل اليدوي مرحلة بمرحلة

### المرحلة 1 — التحميل (CPU، بدون GPU)

حضّر ملف `playLinks.csv`:
```csv
https://www.youtube.com/playlist?list=PL8I2WxsMdus-YeZzTX6JZP7q8gLBfDgxa
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxxxx,VIDEO_ID_1,VIDEO_ID_2
```
- العمود الأول: رابط قائمة التشغيل
- الأعمدة المتبقية: معرفات الفيديوهات المستثناة (اختياري)

```bash
python main.py download playLinks.csv
```

- يحمّل الصوت فقط كـ WAV بجودة 44100Hz أحادي القناة
- يحفظ الملفات في `data/raw_audio/`
- يتجاوز الفيديوهات المحملة مسبقاً تلقائياً

---

### المرحلة 2 — المعالجة (GPU مطلوب)

```bash
python main.py process
```

- يعزل صوت المتكلم بـ **Demucs htdemucs_ft** (إزالة الموسيقى والضوضاء)
- يُقسّم الصوت عند التوقفات الطويلة فقط (الصمت القصير بين الكلام يُدمج)
- ينسخ كل مقطع بـ **WhisperX large-v3** (عربي)
- يدعم الاستئناف — يتجاوز الملفات المعالجة مسبقاً تلقائياً

الناتج:
```
data/vocals/          ← مقاطع صوتية منقّاة
data/transcripts/     ← نص لكل مقطع
data/fulltranscripts/ ← النص الكامل لكل فيديو
data/metadata/        ← tts_metadata.json
```

---

### المرحلة 3 — تشكيل النصوص (اختياري — لضمان دقة النطق)

> **هذه المرحلة اختيارية** — تُحسّن جودة بيانات التدريب بإضافة الحركات للنصوص
> مما يضمن ربطاً دقيقاً بين النص المكتوب والصوت المسموع عند التدريب.

```bash
python diacritize.py
```

- يعرض معاينة على عينة من الملفات أولاً
- يطلب تأكيداً قبل الحفظ الفعلي
- يُعيد معالجة جميع الملفات (بما فيها المشكّلة سابقاً)
- يحفظ نسخة احتياطية من كل ملف بامتداد `.orig` قبل أي تعديل
- يتطلب `secrets/CREDENTIALS.json`

للحفظ المباشر بدون تأكيد:
```bash
python diacritize.py --yes
```

---

### المرحلة 4 — الرفع إلى Kaggle (CPU)

حضّر `config.yaml`:
```yaml
dataset_tts_name: "history-lab-tts-v1"
dataset_llm_name: "history-lab-llm-v1"
```

```bash
python main.py upload
```

- يرفع **TTS Dataset**: vocals + transcripts + metadata
- يرفع **LLM Dataset**: fulltranscripts فقط
- ينشئ dataset جديد أو يُحدّث الموجود تلقائياً
- يتطلب `secrets/kaggle.json`

---

## هيكل البيانات الكامل

```
data/
├── raw_audio/
│   └── VIDEO_ID.wav
├── vocals/
│   ├── VIDEO_ID_000.wav    ← مقطع صوتي منقّى
│   └── ...
├── transcripts/
│   ├── VIDEO_ID_000.txt    ← نص كل مقطع (مشكّل بعد diacritize)
│   ├── VIDEO_ID_000.orig   ← نسخة أصلية قبل التشكيل
│   └── ...
├── fulltranscripts/
│   └── VIDEO_ID.txt        ← النص الكامل للفيديو
└── metadata/
    └── tts_metadata.json   ← metadata موحد
```

---

## ملاحظات

- **المراحل 1 و 3 و 4** لا تحتاج GPU — شغّلها على CPU لتوفير الرصيد
- **المرحلة 2** تحتاج GPU (L40s أو A100 موصى به)
- جميع المراحل تدعم الاستئناف — لن يُعاد معالجة ما تم مسبقاً
- مجلد `secrets/` مُدرج في `.gitignore` ولن يُرفع على GitHub أبداً
