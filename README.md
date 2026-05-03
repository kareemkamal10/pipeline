# History Lab Pipeline 🎙️

Pipeline متكامل لبناء dataset عربي عالي الجودة لتدريب نماذج TTS —
من تحميل الصوت من YouTube حتى الرفع على Kaggle.

---

## هيكل المشروع

```
pipeline/
├── secrets/                   ← مفاتيح API (محمية من GitHub)
│   ├── CREDENTIALS.json       ← Google Cloud / Vertex AI
│   └── kaggle.json            ← Kaggle API
├── data/                      ← البيانات (لا تُرفع على GitHub)
│   ├── raw_audio/             ← WAV خام بعد التحميل
│   ├── vocals/                ← مقاطع منقّاة بعد Demucs
│   ├── transcripts/           ← نص كل مقطع (.txt + .orig)
│   ├── fulltranscripts/       ← النص الكامل لكل فيديو
│   └── metadata/              ← tts_metadata.json
├── main.py                    ← نقطة الدخول الرئيسية
├── downloader.py              ← المرحلة 1: التحميل
├── processor.py               ← المرحلة 2: المعالجة
├── diacritize.py              ← المرحلة 3: التشكيل (مستقلة)
├── uploader.py                ← المرحلة 4: الرفع
├── config_loader.py           ← قراءة مركزية لـ config.yaml
├── run_pipeline.sh            ← تشغيل كامل بأمر واحد
├── config.yaml                ← جميع الإعدادات من مكان واحد
└── playLinks.csv              ← روابط قوائم التشغيل
```

---

## الإعداد الأولي (مرة واحدة)

```bash
pip install -r requirements.txt
apt install ffmpeg -y
mkdir -p secrets
```

**Kaggle** ← من https://www.kaggle.com/settings → API → Create New Token:
```bash
cp /path/to/kaggle.json secrets/kaggle.json
```

**Google Cloud** ← من Google Cloud Console → Service Accounts:
```bash
cp /path/to/your-key.json secrets/CREDENTIALS.json
```

---

## config.yaml — إدارة كل الإعدادات من مكان واحد

هذا هو الملف الوحيد الذي تحتاج تعديله بين الجلسات:

```yaml
# ── اسم الجلسة ──────────────────────────────────────────
# يُستخدم كاسم موحد لكل شيء:
#   - dataset TTS على Kaggle  →  session_name-tts
#   - dataset LLM على Kaggle  →  session_name-llm
# غيّره لكل جلسة تسجيل جديدة
session_name: "history-lab-v1"

# ── مسارات المفاتيح ──────────────────────────────────────
paths:
  data_dir:           "data"
  kaggle_credentials: "secrets/kaggle.json"
  google_credentials: "secrets/CREDENTIALS.json"

# ── إعدادات التقسيم الصوتي ──────────────────────────────
segmentation:
  merge_gap_sec:    3.0   # صمت أقصر → دمج | أطول → قطع
  min_segment_sec:  1.0   # مقاطع أقصر من هذا تُحذف (ضوضاء)
  max_segment_sec:  35.0  # مقاطع أطول من هذا تُقسَّم تلقائياً

# ── إعدادات التشكيل ──────────────────────────────────────
diacritization:
  auto:     false           # true = يعمل تلقائياً بعد المعالجة
  model:    "gemini-2.5-flash"
  location: "us-central1"

# ── إعدادات الرفع ────────────────────────────────────────
upload:
  auto: false               # true = يُرفع تلقائياً بعد الانتهاء
```

### شرح الإعدادات

**`session_name`**
الاسم الفريد للجلسة — يُشتق منه تلقائياً اسما الـ datasets على Kaggle.
مثال: `history-lab-v1` → ينشئ `history-lab-v1-tts` و `history-lab-v1-llm`.

**`segmentation`**

| الإعداد | الوصف | القيمة الافتراضية |
|---------|-------|-----------------|
| `merge_gap_sec` | صمت أقل من هذا يُدمج (توقف طبيعي بين الجمل) — أكثر منه يُعدّ نقطة قطع (مكان موسيقى محذوفة) | `3.0` ث |
| `min_segment_sec` | المقاطع الأقصر من هذا تُحذف (ضوضاء متبقية بعد Demucs) | `1.0` ث |
| `max_segment_sec` | المقاطع الأطول من هذا تُقسَّم تلقائياً بالتساوي | `35.0` ث |

**`diacritization.auto`**
- `false` (افتراضي): يجب تشغيل `python diacritize.py` يدوياً
- `true`: يعمل تلقائياً ضمن `bash run_pipeline.sh` بعد المعالجة

**`upload.auto`**
- `false` (افتراضي): يجب تشغيل `python main.py upload` يدوياً
- `true`: يعمل تلقائياً ضمن `bash run_pipeline.sh` بعد الانتهاء

---

## التشغيل الكامل بأمر واحد

```bash
bash run_pipeline.sh
```

| الخيار | الوصف |
|--------|-------|
| `bash run_pipeline.sh` | يعمل حسب إعدادات config.yaml |
| `bash run_pipeline.sh --skip-diacritize` | يتجاوز التشكيل بغض النظر عن config |
| `bash run_pipeline.sh --skip-upload` | يتجاوز الرفع بغض النظر عن config |
| `bash run_pipeline.sh mylinks.csv` | ملف CSV مخصص |

عند التشغيل يُطبع ملخص الإعدادات الحالية:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  History Lab Pipeline
  الجلسة  : history-lab-v1
  التشكيل : يدوي
  الرفع   : يدوي
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## التشغيل اليدوي مرحلة بمرحلة

### المرحلة 1 — التحميل (CPU)

```bash
python main.py download playLinks.csv
```

صيغة `playLinks.csv`:
```csv
https://www.youtube.com/playlist?list=PLAYLIST_ID
https://www.youtube.com/playlist?list=PLAYLIST_ID,VIDEO_TO_EXCLUDE
```

- يحمّل الصوت فقط كـ WAV أحادي القناة 44100Hz
- يحفظ في `data/raw_audio/`
- يتجاوز الفيديوهات المحملة مسبقاً تلقائياً

---

### المرحلة 2 — المعالجة (GPU مطلوب — L40s موصى به)

```bash
python main.py process
```

ما يحدث بالترتيب:
1. **Demucs htdemucs_ft** — عزل صوت المتكلم وحذف الموسيقى والضوضاء
2. **التقسيم** — حسب إعدادات `segmentation` في config.yaml
3. **WhisperX large-v3** — تفريغ نصي مع حفظ timestamps الكلمات
4. **tts_metadata.json** — ملف موحد لكل المقاطع

يدعم الاستئناف — يتجاوز الملفات المعالجة مسبقاً

---

### المرحلة 3 — التشكيل (CPU — اختياري)

```bash
python diacritize.py        # معاينة ثم تأكيد ثم حفظ
python diacritize.py --yes  # حفظ مباشر بدون تأكيد
```

- يعرض معاينة قبل/بعد على 3 ملفات
- يُحدّث ملفات `.txt` و `tts_metadata.json` بالتزامن
- يحفظ نسخ احتياطية `.orig` قبل أي تعديل
- يتطلب `secrets/CREDENTIALS.json`

---

### المرحلة 4 — الرفع (CPU)

```bash
python main.py upload
```

- يرفع **TTS Dataset** (`session_name-tts`): vocals + transcripts + metadata
- يرفع **LLM Dataset** (`session_name-llm`): fulltranscripts فقط
- ينشئ dataset جديد أو يُحدّث الموجود تلقائياً
- يتطلب `secrets/kaggle.json`

---

## بنية tts_metadata.json

```json
{
  "dataset_name": "history_lab_tts",
  "total_samples": 312,
  "total_hours": 1.8,
  "samples": [
    {
      "video_id":         "AFlCRe-aU7w",
      "segment_id":       12,
      "audio_file":       "vocals/AFlCRe-aU7w_012.wav",
      "text_file":        "transcripts/AFlCRe-aU7w_012.txt",
      "duration_seconds": 28.4,
      "file_size_bytes":  2503680,
      "text":             "وَجَدَ الأَسَدُ فَرِيسَتَهُ عِندَ مَوْرِدِ المَاءِ",
      "word_timestamps": [
        {"word": "وَجَدَ",    "start": 0.0,  "end": 0.42, "score": 0.99},
        {"word": "الأَسَدُ", "start": 0.50, "end": 1.10, "score": 0.97}
      ]
    }
  ]
}
```

---

## جدول المراحل

| المرحلة | GPU | استئناف | المفاتيح المطلوبة |
|---------|-----|---------|------------------|
| التحميل | ❌ | ✅ | — |
| المعالجة | ✅ | ✅ | — |
| التشكيل | ❌ | ✅ | CREDENTIALS.json |
| الرفع | ❌ | — | kaggle.json |

- `secrets/` في `.gitignore` — لن يُرفع على GitHub أبداً
- `data/` في `.gitignore` — احتفظ بنسخة محلية أو على Kaggle
