"""
uploader.py — المرحلة الثالثة
رفع Datasets إلى Kaggle (TTS و LLM)
"""

import json
import subprocess
import yaml
from pathlib import Path


def _check_kaggle_auth() -> bool:
    """التحقق من إعداد Kaggle CLI قبل محاولة الرفع"""
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if not kaggle_json.exists():
        print("\n✗ Kaggle CLI غير مُعدَّة.")
        print("  لإعدادها:")
        print("  1. اذهب إلى https://www.kaggle.com/settings")
        print("  2. قسم API → اضغط Create New Token")
        print("  3. سيتم تحميل ملف kaggle.json")
        print("  4. نفّذ الأوامر التالية:")
        print("       mkdir -p ~/.kaggle")
        print("       cp kaggle.json ~/.kaggle/kaggle.json")
        print("       chmod 600 ~/.kaggle/kaggle.json")
        return False

    result = subprocess.run(
        ["kaggle", "datasets", "list", "--mine", "--max-size", "1"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("\n✗ Kaggle CLI موجودة لكن المصادقة فشلت.")
        print(f"  الخطأ: {result.stderr.strip()}")
        print("  تأكد أن ~/.kaggle/kaggle.json يحتوي بيانات صحيحة.")
        return False

    return True


def upload_datasets(config_path: str = "config.yaml", data_dir: str = "data"):
    """
    رفع Datasets إلى Kaggle بناءً على config.yaml
    - datasetTTS: يحتوي vocals + transcripts + metadata
    - datasetLLM: يحتوي fulltranscripts
    """
    if not _check_kaggle_auth():
        return

    config_file = Path(config_path)
    if not config_file.exists():
        print(f"✗ ملف config {config_path} غير موجود")
        return

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    dataset_tts_name = config.get("dataset_tts_name")
    dataset_llm_name = config.get("dataset_llm_name")

    if not dataset_tts_name or not dataset_llm_name:
        print("✗ لم يتم العثور على dataset_tts_name أو dataset_llm_name في config.yaml")
        return

    data_path = Path(data_dir)
    
    # 1. رفع TTS Dataset
    print(f"\n▶ رفع TTS Dataset: {dataset_tts_name}")
    _upload_tts_dataset(dataset_tts_name, data_path)
    
    # 2. رفع LLM Dataset
    print(f"\n▶ رفع LLM Dataset: {dataset_llm_name}")
    _upload_llm_dataset(dataset_llm_name, data_path)
    
    print("\n✔ انتهى الرفع!")


def _upload_tts_dataset(dataset_name: str, data_path: Path):
    """
    رفع TTS Dataset (vocals + transcripts + metadata)
    """
    print(f"  التحضير...")
    
    # تحقق من وجود الملفات
    vocals_dir = data_path / "vocals"
    transcripts_dir = data_path / "transcripts"
    metadata_file = data_path / "metadata" / "tts_metadata.json"
    
    if not vocals_dir.exists() or not transcripts_dir.exists() or not metadata_file.exists():
        print("  ✗ الملفات المطلوبة غير موجودة")
        return
    
    # إعداد مجلد الرفع
    dataset_dir = data_path / f"kaggle_tts_{dataset_name}"
    dataset_dir.mkdir(exist_ok=True)
    
    # انسخ الملفات
    import shutil
    shutil.copytree(vocals_dir, dataset_dir / "vocals", dirs_exist_ok=True)
    shutil.copytree(transcripts_dir, dataset_dir / "transcripts", dirs_exist_ok=True)
    shutil.copy(metadata_file, dataset_dir / "tts_metadata.json")
    
    # أنشئ dataset.json
    dataset_info = {
        "title": dataset_name,
        "description": "TTS Dataset - صوت + نصوص + metadata",
        "id": f"history-lab/{dataset_name.lower()}",
    }
    with open(dataset_dir / "dataset-metadata.json", "w", encoding="utf-8") as f:
        json.dump(dataset_info, f, ensure_ascii=False, indent=2)
    
    # رفع باستخدام Kaggle CLI
    print(f"  رفع إلى Kaggle...")
    try:
        subprocess.run([
            "kaggle", "datasets", "create",
            "-p", str(dataset_dir),
            "-q"
        ], check=True)
        print(f"  ✔ تم الرفع: {dataset_name}")
    except subprocess.CalledProcessError:
        # محاولة التحديث لو كان موجود
        try:
            print(f"  تحديث الـ Dataset...")
            subprocess.run([
                "kaggle", "datasets", "version",
                "-p", str(dataset_dir),
                "-m", "تحديث جديد"
            ], check=True)
            print(f"  ✔ تم التحديث: {dataset_name}")
        except Exception as e:
            print(f"  ✗ فشل التحديث: {e}")
    except Exception as e:
        print(f"  ✗ فشل الرفع: {e}")


def _upload_llm_dataset(dataset_name: str, data_path: Path):
    """
    رفع LLM Dataset (fulltranscripts فقط)
    """
    print(f"  التحضير...")
    
    # تحقق من وجود الملفات
    fulltranscripts_dir = data_path / "fulltranscripts"
    
    if not fulltranscripts_dir.exists():
        print("  ✗ مجلد fulltranscripts غير موجود")
        return
    
    # إعداد مجلد الرفع
    dataset_dir = data_path / f"kaggle_llm_{dataset_name}"
    dataset_dir.mkdir(exist_ok=True)
    
    # انسخ الملفات
    import shutil
    shutil.copytree(fulltranscripts_dir, dataset_dir / "fulltranscripts", dirs_exist_ok=True)
    
    # أنشئ metadata
    dataset_info = {
        "title": dataset_name,
        "description": "LLM Dataset - نصوص كاملة",
        "id": f"history-lab/{dataset_name.lower()}",
    }
    with open(dataset_dir / "dataset-metadata.json", "w", encoding="utf-8") as f:
        json.dump(dataset_info, f, ensure_ascii=False, indent=2)
    
    # رفع باستخدام Kaggle CLI
    print(f"  رفع إلى Kaggle...")
    try:
        subprocess.run([
            "kaggle", "datasets", "create",
            "-p", str(dataset_dir),
            "-q"
        ], check=True)
        print(f"  ✔ تم الرفع: {dataset_name}")
    except subprocess.CalledProcessError:
        # محاولة التحديث
        try:
            print(f"  تحديث الـ Dataset...")
            subprocess.run([
                "kaggle", "datasets", "version",
                "-p", str(dataset_dir),
                "-m", "تحديث جديد"
            ], check=True)
            print(f"  ✔ تم التحديث: {dataset_name}")
        except Exception as e:
            print(f"  ✗ فشل التحديث: {e}")
    except Exception as e:
        print(f"  ✗ فشل الرفع: {e}")
