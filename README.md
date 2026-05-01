# History Lab Pipeline 🎙️

معالجة تلقائية للمحتوى الصوتي — تحميل، تنقية، ونسخ.

---

## الإعداد الأولي (مرة واحدة فقط)

```bash
# 1. تثبيت المكتبات
pip install -r requirements.txt
apt install ffmpeg -y

# 2. إعداد Kaggle credentials
mkdir -p ~/.kaggle
cp kaggle.json ~/.kaggle/
chmod 600 ~/.kaggle/kaggle.json
```

---

## الاستخدام

### المرحلة 1 — التحميل (CPU، بدون GPU)

**الخطوة الأولى:** تحضير ملف `playLinks.csv`:
```csv
https://www.youtube.com/playlist?list=PL8I2WxsMdus-YeZzTX6JZP7q8gLBfDgxa,AFlCRe-aU7w
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxxxx,VIDEO_ID_1,VIDEO_ID_2
```

**شكل الملف:**
- العمود الأول: رابط قائمة التشغيل
- الأعمدة المتبقية: معرفات الفيديوهات المستثناة (اختياري)

**التشغيل:**
```bash
python main.py download playLinks.csv
```

- يحمّل الصوت فقط كـ WAV بجودة 44100Hz
- يحفظ الملفات في `data/raw_audio/`
- يتجاهل الفيديوهات المستثناة (المذكورة في CSV)
- في مجلد مؤقت يتم حذفه بعد التحويل

---

### المرحلة 2 — المعالجة (GPU مطلوب)

```bash
python main.py process
```

- يعزل صوت المتكلم بـ **Demucs htdemucs_ft**
- **يقسم الصوت عند كل جملة/توقف** (استخدام librosa لاكتشاف الصمت)
- ينسخ كل مقطع صوتي بـ **WhisperX large-v3** (عربي)
- يحفظ:
  - `data/vocals/` — مقاطع صوتية صغيرة (VIDEO_ID_000.wav, VIDEO_ID_001.wav, ...)
  - `data/transcripts/` — نص لكل مقطع (VIDEO_ID_000.txt, VIDEO_ID_001.txt, ...)
  - `data/fulltranscripts/` — النص الكامل (VIDEO_ID.txt)
  - `data/metadata/tts_metadata.json` — ملف metadata موحد (يُحدَّث عند كل جلسة)

---

### المرحلة 3 — رفع النتائج إلى Kaggle

**الخطوة الأولى:** تحضير `config.yaml`:
```yaml
dataset_tts_name: "history-lab-tts-v1"
dataset_llm_name: "history-lab-llm-v1"
```

**التشغيل:**
```bash
python main.py upload
```

- يرفع **TTS Dataset**: vocals + transcripts + metadata
- يرفع **LLM Dataset**: fulltranscripts فقط
- لو كان الاسم جديد: ينشئ dataset جديد
- لو كان موجود: يحدث الـ dataset الموجود

---

## هيكل البيانات

```
data/
├── raw_audio/
│   ├── VIDEO_ID_1.wav
│   ├── VIDEO_ID_2.wav
│   └── ...
├── vocals/
│   ├── VIDEO_ID_1_000.wav    ← مقطع صوتي منقى (عند كل جملة/توقف)
│   ├── VIDEO_ID_1_001.wav
│   ├── VIDEO_ID_2_000.wav
│   └── ...
├── transcripts/
│   ├── VIDEO_ID_1_000.txt    ← نص لكل مقطع صوتي
│   ├── VIDEO_ID_1_001.txt
│   ├── VIDEO_ID_2_000.txt
│   └── ...
├── fulltranscripts/
│   ├── VIDEO_ID_1.txt        ← النص الكامل
│   ├── VIDEO_ID_2.txt
│   └── ...
└── metadata/
    └── tts_metadata.json     ← metadata واحد للجلسة (يُحدَّث عند كل معالجة جديدة)
```

**ملف metadata الواحد (tts_metadata.json):**
- يحتوي على كل الفيديوهات والمقاطع الصوتية في الجلسة الحالية
- عند إضافة جلسة جديدة (تكملة لـ dataset موجود): يتم سحب ملف metadata القديم وتحديثه بالبيانات الجديدة
- يحتفظ بـ: حجم الملفات، عدد الساعات، ربط صوت↔نص لكل مقطع

---

## ملاحظات

- **المرحلة 1** لا تحتاج GPU — شغّلها على CPU لتوفير الرصيد
- **المرحلة 2** تحتاج GPU (L40s أو A100 موصى به)
- الـ `tracker.json` هو الحارس — لن يتم تحميل أو معالجة أي شيء مرتين
