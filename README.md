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

```bash
python main.py download \
  --session batch_01 \
  --playlists "https://youtube.com/playlist?list=XXX" "https://youtube.com/playlist?list=YYY"
```

- يحمّل الصوت كـ WAV بجودة 44100Hz
- يحفظ الملفات في `./data/batch_01/raw_audio/`
- يسجل كل playlist وفيديو في `tracker.json`
- **لن يعيد تحميل playlist تم تحميلها بالفعل**

---

### المرحلة 2 — المعالجة (GPU مطلوب)

```bash
python main.py process --session batch_01
```

- يعزل صوت المعلق بـ **Demucs htdemucs_ft**
- ينسخ الكلام بـ **WhisperX large-v3** (عربي)
- يحفظ:
  - `./data/batch_01/vocals/` — الصوت المنقى
  - `./data/batch_01/transcripts/*.json` — word-level timestamps
  - `./data/batch_01/transcripts/*.txt` — النص الكامل
- **لن يعيد معالجة فيديو تمت معالجته بالفعل**

---

### رفع النتائج إلى Kaggle

```bash
python main.py upload \
  --session batch_01 \
  --dataset history-lab-batch-01
```

- كل جلسة → Dataset مستقل باسمها
- يرفع الصوت المنقى والنصوص معاً

---

### عرض حالة الجلسة

```bash
python main.py status --session batch_01
```

---

## هيكل البيانات

```
data/
└── batch_01/
    ├── tracker.json          ← سجل الحالة
    ├── raw_audio/
    │   └── PLAYLIST_ID/
    │       └── VIDEO_ID.wav
    ├── vocals/
    │   └── VIDEO_ID.wav      ← صوت منقى
    └── transcripts/
        ├── VIDEO_ID.json     ← word timestamps
        └── VIDEO_ID.txt      ← نص كامل
```

---

## ملاحظات

- **المرحلة 1** لا تحتاج GPU — شغّلها على CPU لتوفير الرصيد
- **المرحلة 2** تحتاج GPU (L40s أو A100 موصى به)
- الـ `tracker.json` هو الحارس — لن يتم تحميل أو معالجة أي شيء مرتين
