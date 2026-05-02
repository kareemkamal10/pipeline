"""
diacritize.py — خدمة تشكيل النصوص العربية مستقلة عن الـ pipeline الرئيسي

تعمل على ملفات data/transcripts/ وتُشكّل كل ملف باستخدام Gemini 2.5 Flash
عبر Vertex AI، ثم تحفظ النتيجة في مكانها مباشرة.

الاستخدام:
    python diacritize.py
    python diacritize.py --data-dir /path/to/data
    python diacritize.py --resume         # تجاوز الملفات المشكّلة مسبقاً
    python diacritize.py --dry-run        # معاينة بدون حفظ
"""

import argparse
import json
import time
import traceback
from pathlib import Path

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

# ── إعدادات Vertex AI ────────────────────────────────────────────────────────

VERTEX_PROJECT_ID = None   # يُقرأ من key.json تلقائياً إذا كان None
VERTEX_LOCATION   = "us-central1"
GEMINI_MODEL      = "gemini-2.5-flash"

# ── إعدادات المعالجة ──────────────────────────────────────────────────────────

REQUESTS_PER_MINUTE = 50        # حد آمن تحت الـ rate limit
DELAY_BETWEEN_REQUESTS = 60 / REQUESTS_PER_MINUTE
BACKUP_SUFFIX = ".orig"         # لحفظ نسخة أصلية قبل التعديل

# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """أنت أداة تشكيل نصوص عربية متخصصة. مهمتك محددة جداً وصارمة.

## مهمتك الوحيدة
تشكيل النص العربي بإضافة الحركات (الفتحة، الضمة، الكسرة، السكون، الشدة، التنوين) في المواضع التي يكون فيها غيابها مصدر لبس في النطق.

## القواعد الصارمة
1. **لا تغيّر أي كلمة** — لا تحذف، لا تضيف، لا تعيد صياغة، لا تصحح أخطاء إملائية.
2. **لا تُعلّق ولا تشرح** — أخرج النص المشكّل فقط، بلا مقدمة ولا خاتمة.
3. **الكلمات الواضحة** — إذا كانت الكلمة واضحة النطق من سياقها دون تشكيل، فالتشكيل اختياري.
4. **عند الشك** — اترك الكلمة بدون تشكيل. الخطأ في التشكيل أسوأ من غيابه.
5. **لا تُشكّل الأعلام والأسماء الأجنبية** — اتركها كما هي.
6. **النص مصدره تفريغ صوتي** — قد يحتوي على أخطاء إملائية بسيطة، تجاهلها ولا تصححها.

## مثال
الإدخال:  وجد الاسد فريسته عند مورد الماء فانقض عليها بسرعة
الإخراج: وَجَدَ الأَسَدُ فَرِيسَتَهُ عِندَ مَوْرِدِ المَاءِ فَانْقَضَّ عَلَيْهَا بِسُرْعَةٍ

أخرج النص المشكّل فقط."""

# ── دوال مساعدة ──────────────────────────────────────────────────────────────


def load_vertex_project(key_path: Path) -> str:
    """قراءة project_id من ملف key.json"""
    with open(key_path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("project_id") or data.get("quota_project_id", "")


def init_vertex(key_path: Path | None = None) -> GenerativeModel:
    """تهيئة Vertex AI وإرجاع نموذج Gemini"""
    import os

    # ابحث عن key.json
    candidates = [
        key_path,
        Path("key.json"),
        Path("service_account.json"),
        Path.home() / "key.json",
    ]
    found_key = next((p for p in candidates if p and p.exists()), None)

    if found_key:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(found_key)
        project_id = VERTEX_PROJECT_ID or load_vertex_project(found_key)
        print(f"  ✔ مفتاح Vertex AI: {found_key}")
        print(f"  ✔ Project: {project_id}")
    else:
        # افترض أن البيئة مُعدَّة (ADC)
        project_id = VERTEX_PROJECT_ID or ""
        print("  ⚠ لم يُعثر على key.json — يُستخدم Application Default Credentials")

    vertexai.init(project=project_id, location=VERTEX_LOCATION)

    model = GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
    )
    return model


def diacritize_text(model: GenerativeModel, text: str) -> str | None:
    """
    إرسال نص إلى Gemini للتشكيل.
    يُرجع النص المشكّل، أو None عند الفشل.
    """
    text = text.strip()
    if not text:
        return text

    # نص قصير جداً → أرجعه كما هو
    if len(text) < 5:
        return text

    try:
        response = model.generate_content(
            text,
            generation_config=GenerationConfig(
                temperature=0.0,       # صفر تماماً — لا إبداع، فقط تشكيل
                max_output_tokens=512,
                candidate_count=1,
            ),
        )

        result = response.text.strip()

        # فحص سلامة المخرج — يجب ألا يكون أطول بكثير من الإدخال
        # (مؤشر على هلوسة أو شرح غير مطلوب)
        input_words  = len(text.split())
        output_words = len(result.split())

        if output_words > input_words * 1.3:
            print(f"    ⚠ المخرج أطول من المتوقع ({output_words} كلمة مقابل {input_words}) — تجاهل")
            return None

        # فحص: هل احتوى المخرج على نص عربي أصلاً؟
        arabic_chars = sum(1 for c in result if "\u0600" <= c <= "\u06FF")
        if arabic_chars < 3:
            print("    ⚠ المخرج لا يحتوي على عربية — تجاهل")
            return None

        return result

    except Exception as e:
        print(f"    ✗ خطأ من Gemini: {e}")
        return None


def is_already_diacritized(text: str, threshold: float = 0.15) -> bool:
    """
    كشف إذا كان النص مشكّلاً مسبقاً.
    threshold: نسبة حروف التشكيل إلى حروف العربية.
    """
    arabic_letters = sum(1 for c in text if "\u0621" <= c <= "\u064A")
    diacritics     = sum(1 for c in text if "\u064B" <= c <= "\u065F")

    if arabic_letters == 0:
        return False
    return (diacritics / arabic_letters) >= threshold


# ── الدالة الرئيسية ───────────────────────────────────────────────────────────


def diacritize_all(
    data_dir: str = "data",
    key_path: Path | None = None,
    resume: bool = True,
    dry_run: bool = False,
    backup: bool = True,
):
    """
    معالجة جميع ملفات data/transcripts/ وتشكيلها.

    المعاملات:
        data_dir : مجلد data الرئيسي
        key_path : مسار key.json (اختياري)
        resume   : تجاوز الملفات المشكّلة مسبقاً
        dry_run  : معاينة فقط بدون حفظ
        backup   : حفظ نسخة أصلية بامتداد .orig
    """
    transcripts_dir = Path(data_dir) / "transcripts"

    if not transcripts_dir.exists():
        print(f"✗ المجلد غير موجود: {transcripts_dir}")
        return

    txt_files = sorted(transcripts_dir.glob("*.txt"))
    # استبعد ملفات النسخ الاحتياطية
    txt_files = [f for f in txt_files if not f.name.endswith(BACKUP_SUFFIX)]

    if not txt_files:
        print("✗ لا توجد ملفات نصية في transcripts/")
        return

    print(f"\n▶ تشكيل النصوص")
    print(f"  الموديل  : {GEMINI_MODEL}")
    print(f"  الملفات  : {len(txt_files)}")
    print(f"  dry-run  : {'نعم' if dry_run else 'لا'}")
    print(f"  استئناف  : {'نعم' if resume else 'لا'}")

    # تهيئة Vertex AI
    print("\n▶ تهيئة Vertex AI...")
    try:
        model = init_vertex(key_path)
        print(f"  ✔ النموذج جاهز: {GEMINI_MODEL}")
    except Exception as e:
        print(f"  ✗ فشل تهيئة Vertex AI: {e}")
        traceback.print_exc()
        return

    # إحصاءات
    stats = {"skipped": 0, "processed": 0, "failed": 0, "unchanged": 0}
    t_start = time.time()

    for i, txt_file in enumerate(txt_files, 1):
        text = txt_file.read_text(encoding="utf-8").strip()

        prefix = f"  [{i:04d}/{len(txt_files)}] {txt_file.name}"

        # تجاوز الملفات الفارغة
        if not text:
            print(f"{prefix} — فارغ، تجاوز")
            stats["skipped"] += 1
            continue

        # تجاوز المشكّلة مسبقاً إذا كان resume مفعّلاً
        if resume and is_already_diacritized(text):
            stats["skipped"] += 1
            continue

        # طلب Gemini
        result = diacritize_text(model, text)

        if result is None:
            print(f"{prefix} — ✗ فشل")
            stats["failed"] += 1
        elif result == text:
            print(f"{prefix} — لم يتغير")
            stats["unchanged"] += 1
        else:
            print(f"{prefix} — ✔ تم التشكيل")
            if not dry_run:
                # حفظ نسخة احتياطية
                if backup and not txt_file.with_suffix(BACKUP_SUFFIX).exists():
                    txt_file.with_suffix(BACKUP_SUFFIX).write_text(
                        text, encoding="utf-8"
                    )
                # حفظ النص المشكّل
                txt_file.write_text(result, encoding="utf-8")
            stats["processed"] += 1

        # rate limiting
        if i < len(txt_files):
            time.sleep(DELAY_BETWEEN_REQUESTS)

    elapsed = time.time() - t_start
    print(f"\n✔ اكتمل في {elapsed:.1f} ثانية")
    print(f"   تم تشكيله  : {stats['processed']}")
    print(f"   لم يتغير   : {stats['unchanged']}")
    print(f"   تجاوز      : {stats['skipped']}")
    print(f"   فشل        : {stats['failed']}")

    if dry_run:
        print("\n   ⚠ dry-run — لم يُحفظ أي شيء")


# ── نقطة الدخول ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="تشكيل ملفات transcripts باستخدام Gemini على Vertex AI"
    )
    parser.add_argument(
        "--data-dir", default="data",
        help="مجلد data الرئيسي (افتراضي: data)"
    )
    parser.add_argument(
        "--key", default=None,
        help="مسار ملف key.json (افتراضي: يبحث تلقائياً)"
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="إعادة معالجة الملفات المشكّلة مسبقاً"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="معاينة فقط بدون حفظ"
    )
    parser.add_argument(
        "--no-backup", action="store_true",
        help="عدم حفظ نسخ احتياطية .orig"
    )
    args = parser.parse_args()

    diacritize_all(
        data_dir=args.data_dir,
        key_path=Path(args.key) if args.key else None,
        resume=not args.no_resume,
        dry_run=args.dry_run,
        backup=not args.no_backup,
    )
