"""
uploader.py — المرحلة الثالثة
رفع Datasets إلى Kaggle (TTS و LLM)
"""

import json
import subprocess
import yaml
from pathlib import Path


def _get_kaggle_username() -> str:
    """قراءة username من secrets/kaggle.json"""
    with open(KAGGLE_JSON, encoding="utf-8") as f:
        return json.load(f)["username"]


SECRETS_DIR = Path(__file__).parent / "secrets"
KAGGLE_JSON  = config_loader.kaggle_credentials()


def _check_kaggle_auth() -> bool:
    """التحقق من إعداد Kaggle CLI قبل محاولة الرفع"""
    if not KAGGLE_JSON.exists():
        print("\n✗ ملف secrets/kaggle.json غير موجود.")
        print("  لإعداده:")
        print("  1. اذهب إلى https://www.kaggle.com/settings → API → Create New Token")
        print("  2. ضع الملف المُحمَّل في:  secrets/kaggle.json")
        return False

    import os
    os.environ["KAGGLE_CONFIG_DIR"] = str(SECRETS_DIR)

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

    config = config_loader.load()
    dataset_tts_name = config_loader.tts_dataset_name()
    dataset_llm_name = config_loader.llm_dataset_name()
    data_path        = config_loader.data_dir()
    
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
        "id": f"{_get_kaggle_username()}/{dataset_name.lower()}",
        "licenses": [{"name": "CC0-1.0"}],
    }
    with open(dataset_dir / "dataset-metadata.json", "w", encoding="utf-8") as f:
        json.dump(dataset_info, f, ensure_ascii=False, indent=2)

    # رفع باستخدام Kaggle CLI
    print(f"  رفع إلى Kaggle...")
    try:
        subprocess.run([
            "kaggle", "datasets", "create",
            "-p", str(dataset_dir),
            "--dir-mode", "zip",
            "-q"
        ], check=True)
        print(f"  ✔ تم الإنشاء: {dataset_name}")
    except subprocess.CalledProcessError:
        # Dataset موجود مسبقاً → حدّث نسخة جديدة
        try:
            print(f"  Dataset موجود — تحديث نسخة جديدة...")
            subprocess.run([
                "kaggle", "datasets", "version",
                "-p", str(dataset_dir),
                "--dir-mode", "zip",
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
        "id": f"{_get_kaggle_username()}/{dataset_name.lower()}",
        "licenses": [{"name": "CC0-1.0"}],
    }
    with open(dataset_dir / "dataset-metadata.json", "w", encoding="utf-8") as f:
        json.dump(dataset_info, f, ensure_ascii=False, indent=2)
    
    # رفع باستخدام Kaggle CLI
    print(f"  رفع إلى Kaggle...")
    try:
        subprocess.run([
            "kaggle", "datasets", "create",
            "-p", str(dataset_dir),
            "--dir-mode", "zip",
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
                "--dir-mode", "zip",
                "-m", "تحديث جديد"
            ], check=True)
            print(f"  ✔ تم التحديث: {dataset_name}")
        except Exception as e:
            print(f"  ✗ فشل التحديث: {e}")
    except Exception as e:
        print(f"  ✗ فشل الرفع: {e}")
