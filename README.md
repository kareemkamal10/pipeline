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
├── uploader.py                ← المرحلة 4: الرفع
├── diacritize.py              ← المرحلة 3: التشكيل (مستقلة)
├── run_pipeline.sh            ← تشغيل كامل بأمر واحد
├── playLinks.csv              ← روابط قوائم التشغيل
└── config.yaml                ← أسماء Datasets على Kaggle
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

## التشغيل الكامل بأمر واحد

```bash
bash run_pipeline.sh
```

| الخيار | الوصف |
|--------|-------|
| `bash run_pipeline.sh` | كامل — تحميل + معالجة + تشكيل + رفع |
| `bash run_pipeline.sh --skip-diacritize` | بدون خطوة التشكيل |
| `bash run_pipeline.sh --skip-upload` | بدون رفع Kaggle |
| `bash run_pipeline.sh mylinks.csv` | ملف CSV مخصص |

---

## التشغيل اليدوي مرحلة بمرحلة

### المرحلة 1 — التحميل (CPU)

```bash
python main.py download playLinks.csv
```

صيغة `playLinks.csv`:
```csv
https://www.youtube.com/playlist?list=PLAYLIST_ID
https://www.youtube.com/playlist?list=PLAYLIST_ID,VIDEO_TO_EXCLUDE_1,VIDEO_TO_EXCLUDE_2
```

- يحمّل الصوت فقط كـ WAV أحادي القناة 44100Hz
- يحفظ في `data/raw_audio/`
- **يتجاوز الفيديوهات المحملة مسبقاً تلقائياً**

---

### المرحلة 2 — المعالجة (GPU مطلوب — L40s موصى به)

```bash
python main.py process
```

ما يحدث بالترتيب:
1. **Demucs htdemucs_ft** — عزل صوت المتكلم وحذف الموسيقى والضوضاء
2. **التقسيم** — قطع عند الصمت الطويل فقط (> 3 ثوانٍ)، دمج التوقفات القصيرة داخل الكلام، استهداف 20-35 ثانية لكل مقطع
3. **WhisperX large-v3** — تفريغ نصي مع حفظ timestamps الكلمات
4. **tts_metadata.json** — ملف موحد يحتوي كل المقاطع مع timestamps

الناتج:
```
data/vocals/VIDEO_ID_000.wav        ← مقطع صوتي منقّى (20-35 ث)
data/transcripts/VIDEO_ID_000.txt   ← نص المقطع
data/fulltranscripts/VIDEO_ID.txt   ← النص الكامل للفيديو
data/metadata/tts_metadata.json     ← metadata موحد (انظر البنية أدناه)
```

**يدعم الاستئناف** — يتجاوز الملفات المعالجة مسبقاً

---

### المرحلة 3 — التشكيل (CPU — اختياري لكن موصى به)

> تُحسّن جودة التدريب بإضافة الحركات للنصوص العربية.
> تضمن تطابقاً دقيقاً بين النص المكتوب والصوت المسموع.

```bash
python diacritize.py
```

المسار:
1. تعرض معاينة على 3 ملفات (قبل/بعد) للتحقق
2. تطلب تأكيداً قبل الحفظ
3. تُشكّل جميع الملفات وتحفظها
4. **تُحدّث `tts_metadata.json` بالتزامن** — حقل `text` في كل مقطع يُحدَّث بالنص المشكّل، `word_timestamps` تبقى كما هي

النسخ الاحتياطية:
```
transcripts/VIDEO_ID_000.orig        ← النص الأصلي قبل التشكيل
metadata/tts_metadata.json.orig      ← metadata قبل التشكيل
```

للتشغيل بدون تأكيد (داخل scripts):
```bash
python diacritize.py --yes
```

يتطلب: `secrets/CREDENTIALS.json`

---

### المرحلة 4 — الرفع إلى Kaggle (CPU)

```bash
python main.py upload
```

اضبط `config.yaml` أولاً:
```yaml
dataset_tts_name: "history-lab-tts-v1"
dataset_llm_name: "history-lab-llm-v1"
```

- يرفع **TTS Dataset**: vocals + transcripts + tts_metadata.json
- يرفع **LLM Dataset**: fulltranscripts فقط
- ينشئ dataset جديد أو يُحدّث الموجود تلقائياً

يتطلب: `secrets/kaggle.json`

---

## بنية tts_metadata.json

```json
{
  "dataset_name": "history_lab_tts",
  "total_samples": 312,
  "total_hours": 1.8,
  "samples": [
    {
      "video_id":        "AFlCRe-aU7w",
      "segment_id":      12,
      "audio_file":      "vocals/AFlCRe-aU7w_012.wav",
      "text_file":       "transcripts/AFlCRe-aU7w_012.txt",
      "duration_seconds": 28.4,
      "file_size_bytes": 2503680,
      "text":            "وَجَدَ الأَسَدُ فَرِيسَتَهُ عِندَ مَوْرِدِ المَاءِ",
      "word_timestamps": [
        {"word": "وَجَدَ",    "start": 0.0,  "end": 0.42, "score": 0.99},
        {"word": "الأَسَدُ", "start": 0.50, "end": 1.10, "score": 0.97}
      ]
    }
  ]
}
```

---

## ملاحظات تشغيلية

| المرحلة | GPU | الاستئناف | المفاتيح المطلوبة |
|---------|-----|-----------|------------------|
| التحميل | ❌ | ✅ | — |
| المعالجة | ✅ L40s | ✅ | — |
| التشكيل | ❌ | ✅ | CREDENTIALS.json |
| الرفع | ❌ | — | kaggle.json |

- مجلد `secrets/` في `.gitignore` — لن يُرفع على GitHub أبداً
- مجلد `data/` في `.gitignore` — احتفظ بنسخة محلية أو على Kaggle
