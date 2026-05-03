"""
diacritize.py — خدمة تشكيل النصوص العربية مستقلة عن الـ pipeline الرئيسي

تعمل على ملفات data/transcripts/ وتُشكّل كل ملف باستخدام Gemini 2.5 Flash
عبر Vertex AI، ثم تحفظ النتيجة في مكانها مباشرة.

المفاتيح المطلوبة في مجلد secrets/:
    secrets/CREDENTIALS.json  ← Google Cloud Vertex AI

الاستخدام:
    python diacritize.py                 # معاينة أولاً ثم تأكيد ثم حفظ (الافتراضي)
    python diacritize.py --data-dir /x  # تحديد مجلد data مختلف
    python diacritize.py --yes          # تخطي التأكيد والحفظ مباشرة
"""

import argparse
import json
import os
import time
import traceback
from pathlib import Path
import config_loader

# ── مسارات المفاتيح ───────────────────────────────────────────────────────────

SECRETS_DIR      = Path(__file__).parent / "secrets"
CREDENTIALS_JSON = config_loader.google_credentials()

# ── إعدادات Vertex AI ────────────────────────────────────────────────────────

_dia_cfg        = config_loader.diacritization()
VERTEX_LOCATION = _dia_cfg.get("location", "us-central1")
GEMINI_MODEL    = _dia_cfg.get("model",    "gemini-2.5-flash")

# ── إعدادات المعالجة ──────────────────────────────────────────────────────────

REQUESTS_PER_MINUTE   = 50
DELAY_BETWEEN_REQUESTS = 60 / REQUESTS_PER_MINUTE
BACKUP_SUFFIX         = ".orig"
PREVIEW_SAMPLE_COUNT  = 3       # عدد الملفات التي تُعرض في المعاينة

# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """أنت أداة تشكيل نصوص عربية متخصصة. مهمتك محددة جداً وصارمة.

## مهمتك الوحيدة
تشكيل النص العربي بإضافة الحركات (الفتحة، الضمة، الكسرة، السكون، الشدة، التنوين)
في المواضع التي يكون فيها غيابها مصدر لبس في النطق.

## القواعد الصارمة
1. لا تغيّر أي كلمة — لا تحذف، لا تضيف، لا تعيد صياغة، لا تصحح أخطاء إملائية.
2. لا تُعلّق ولا تشرح — أخرج النص المشكّل فقط، بلا مقدمة ولا خاتمة.
3. الكلمات الواضحة — إذا كانت واضحة النطق من سياقها دون تشكيل، فالتشكيل اختياري.
4. عند الشك — اترك الكلمة بدون تشكيل. الخطأ في التشكيل أسوأ من غيابه.
5. لا تُشكّل الأعلام والأسماء الأجنبية — اتركها كما هي.
6. النص مصدره تفريغ صوتي — قد يحتوي على أخطاء إملائية بسيطة، تجاهلها تماماً.

## مثال
الإدخال:  وجد الاسد فريسته عند مورد الماء فانقض عليها بسرعة
الإخراج: وَجَدَ الأَسَدُ فَرِيسَتَهُ عِندَ مَوْرِدِ المَاءِ فَانْقَضَّ عَلَيْهَا بِسُرْعَةٍ

أخرج النص المشكّل فقط."""


# ── تهيئة Vertex AI ───────────────────────────────────────────────────────────

def init_model():
    """تهيئة Vertex AI وإرجاع نموذج Gemini"""
    import vertexai
    from vertexai.generative_models import GenerativeModel

    if not CREDENTIALS_JSON.exists():
        raise FileNotFoundError(
            f"ملف المفتاح غير موجود: {CREDENTIALS_JSON}\n"
            "ضع CREDENTIALS.json في مجلد secrets/"
        )

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(CREDENTIALS_JSON)

    with open(CREDENTIALS_JSON, encoding="utf-8") as f:
        creds = json.load(f)
    project_id = creds.get("project_id") or creds.get("quota_project_id", "")

    print(f"  ✔ CREDENTIALS.json: {CREDENTIALS_JSON}")
    print(f"  ✔ Project: {project_id}")

    vertexai.init(project=project_id, location=VERTEX_LOCATION)
    return GenerativeModel(model_name=GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)


# ── دوال مساعدة ──────────────────────────────────────────────────────────────

def diacritize_text(model, text: str) -> str | None:
    """إرسال نص إلى Gemini للتشكيل. يُرجع النص المشكّل أو None عند الفشل."""
    from vertexai.generative_models import GenerationConfig

    text = text.strip()
    if not text or len(text) < 5:
        return text

    try:
        response = model.generate_content(
            text,
            generation_config=GenerationConfig(
                temperature=0.0,
                max_output_tokens=512,
                candidate_count=1,
            ),
        )
        result = response.text.strip()

        # فحص: المخرج أطول بكثير → هلوسة
        if len(result.split()) > len(text.split()) * 1.3:
            return None

        # فحص: لا يحتوي على عربية
        if sum(1 for c in result if "\u0600" <= c <= "\u06FF") < 3:
            return None

        return result

    except Exception as e:
        print(f"    ✗ خطأ Gemini: {e}")
        return None


def is_diacritized(text: str, threshold: float = 0.15) -> bool:
    """كشف إذا كان النص مشكّلاً مسبقاً"""
    letters    = sum(1 for c in text if "\u0621" <= c <= "\u064A")
    diacritics = sum(1 for c in text if "\u064B" <= c <= "\u065F")
    return letters > 0 and (diacritics / letters) >= threshold


# ── الدالة الرئيسية ───────────────────────────────────────────────────────────

def _load_metadata(metadata_file: Path) -> dict:
    """تحميل tts_metadata.json وبناء فهرس سريع segment_key → index"""
    if not metadata_file.exists():
        return {"data": None, "index": {}}
    with open(metadata_file, encoding="utf-8") as f:
        data = json.load(f)
    index = {}
    for i, sample in enumerate(data.get("samples", [])):
        key = f"{sample['video_id']}_{sample['segment_id']:03d}"
        index[key] = i
    return {"data": data, "index": index}


def _sync_metadata(metadata_file: Path, segment_key: str,
                   new_text: str, metadata_cache: dict) -> None:
    """
    تحديث حقل text في tts_metadata.json للمقطع المحدد.
    word_timestamps تبقى كما هي — التشكيل يغير النص فقط لا التوقيت.
    """
    if metadata_cache["data"] is None:
        return
    idx = metadata_cache["index"].get(segment_key)
    if idx is None:
        return
    metadata_cache["data"]["samples"][idx]["text"] = new_text


def run(data_dir: str = "data", auto_yes: bool = False):
    """
    المسار الكامل:
    1. معاينة (dry-run) على عينة من الملفات
    2. طلب تأكيد من المستخدم
    3. معالجة وحفظ الملفات النصية + تحديث tts_metadata.json بالتزامن
    """
    data_path       = Path(data_dir)
    transcripts_dir = data_path / "transcripts"
    metadata_file   = data_path / "metadata" / "tts_metadata.json"

    if not transcripts_dir.exists():
        print(f"✗ المجلد غير موجود: {transcripts_dir}")
        return

    txt_files = sorted(f for f in transcripts_dir.glob("*.txt")
                       if not f.name.endswith(BACKUP_SUFFIX))

    if not txt_files:
        print("✗ لا توجد ملفات نصية في transcripts/")
        return

    # تحميل metadata مرة واحدة في الذاكرة
    metadata_cache = _load_metadata(metadata_file)
    has_metadata   = metadata_cache["data"] is not None
    if has_metadata:
        print(f"  ✔ tts_metadata.json محمّل ({len(metadata_cache['index'])} مقطع)")
    else:
        print(f"  ⚠ tts_metadata.json غير موجود — سيتم تحديث ملفات .txt فقط")

    print(f"\n▶ تشكيل النصوص — {GEMINI_MODEL}")
    print(f"  الملفات: {len(txt_files)}")

    # ── تهيئة النموذج ─────────────────────────────────────────────────────────
    print("\n▶ تهيئة Vertex AI...")
    try:
        model = init_model()
        print(f"  ✔ النموذج جاهز\n")
    except Exception as e:
        print(f"  ✗ {e}")
        return

    # ── مرحلة المعاينة ────────────────────────────────────────────────────────
    print("━" * 55)
    print(f"  معاينة على {PREVIEW_SAMPLE_COUNT} ملفات قبل الحفظ")
    print("━" * 55)

    for f in txt_files[:PREVIEW_SAMPLE_COUNT]:
        text = f.read_text(encoding="utf-8").strip()
        if not text:
            continue
        result = diacritize_text(model, text)
        print(f"\n  [{f.name}]")
        print(f"  قبل : {text[:120]}")
        print(f"  بعد : {result[:120] if result else '✗ فشل'}")
        time.sleep(DELAY_BETWEEN_REQUESTS)

    # ── طلب التأكيد ────────────────────────────────────────────────────────────
    print("\n" + "━" * 55)
    if not auto_yes:
        try:
            confirm = input("  هل تريد المتابعة وحفظ جميع الملفات؟ [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  ✗ تم الإلغاء.")
            return
        if confirm not in ("y", "yes", "نعم"):
            print("  ✗ تم الإلغاء.")
            return

    # ── مرحلة المعالجة الكاملة ────────────────────────────────────────────────
    print(f"\n▶ بدء معالجة {len(txt_files)} ملف...")
    stats = {"processed": 0, "unchanged": 0, "failed": 0}

    for i, txt_file in enumerate(txt_files, 1):
        # segment_key = VIDEO_ID_012 (بدون .txt)
        segment_key = txt_file.stem
        text        = txt_file.read_text(encoding="utf-8").strip()
        prefix      = f"  [{i:04d}/{len(txt_files)}] {txt_file.name}"

        if not text:
            continue

        result = diacritize_text(model, text)

        if result is None:
            print(f"{prefix} — ✗ فشل")
            stats["failed"] += 1
        elif result == text:
            stats["unchanged"] += 1
        else:
            # 1. نسخة احتياطية للملف النصي
            backup = txt_file.with_suffix(BACKUP_SUFFIX)
            if not backup.exists():
                backup.write_text(text, encoding="utf-8")

            # 2. تحديث الملف النصي
            txt_file.write_text(result, encoding="utf-8")

            # 3. تحديث حقل text في metadata (في الذاكرة)
            _sync_metadata(metadata_file, segment_key, result, metadata_cache)

            print(f"{prefix} — ✔")
            stats["processed"] += 1

        if i < len(txt_files):
            time.sleep(DELAY_BETWEEN_REQUESTS)

    # ── حفظ metadata المحدَّث ─────────────────────────────────────────────────
    if has_metadata and stats["processed"] > 0:
        # نسخة احتياطية لـ metadata
        metadata_backup = metadata_file.with_suffix(".json.orig")
        if not metadata_backup.exists():
            import shutil
            shutil.copy2(metadata_file, metadata_backup)

        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata_cache["data"], f, ensure_ascii=False, indent=2)
        print(f"\n  ✔ tts_metadata.json مُحدَّث بالنصوص المشكّلة")

    print(f"\n✔ اكتمل التشكيل!")
    print(f"   تم تشكيله : {stats['processed']}")
    print(f"   لم يتغير  : {stats['unchanged']}")
    print(f"   فشل       : {stats['failed']}")
    print(f"   النسخ الاحتياطية: .orig و tts_metadata.json.orig")


# ── نقطة الدخول ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="تشكيل ملفات transcripts باستخدام Gemini 2.5 Flash على Vertex AI"
    )
    parser.add_argument("--data-dir", default="data", help="مجلد data (افتراضي: data)")
    parser.add_argument("--yes", "-y", action="store_true", help="تخطي التأكيد والحفظ مباشرة")
    args = parser.parse_args()

    run(data_dir=args.data_dir, auto_yes=args.yes)
