"""
config_loader.py — قراءة مركزية لـ config.yaml
يستخدمه كل ملف في المشروع بدلاً من قراءة yaml مباشرة.
"""

from pathlib import Path
import yaml

_CONFIG_PATH = Path(__file__).parent / "config.yaml"
_cache: dict | None = None


def load() -> dict:
    """تحميل config.yaml مع cache (يُقرأ مرة واحدة فقط)"""
    global _cache
    if _cache is None:
        if not _CONFIG_PATH.exists():
            raise FileNotFoundError(f"config.yaml غير موجود في {_CONFIG_PATH}")
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            _cache = yaml.safe_load(f)
    return _cache


# ── دوال مساعدة للوصول السريع ────────────────────────────

def session_name() -> str:
    return load()["session_name"]

def data_dir() -> Path:
    return Path(load()["paths"]["data_dir"])

def kaggle_credentials() -> Path:
    return Path(load()["paths"]["kaggle_credentials"])

def google_credentials() -> Path:
    return Path(load()["paths"]["google_credentials"])

def segmentation() -> dict:
    return load()["segmentation"]

def diacritization() -> dict:
    return load()["diacritization"]

def upload_config() -> dict:
    return load()["upload"]

def tts_dataset_name() -> str:
    return f"{session_name()}-tts"

def llm_dataset_name() -> str:
    return f"{session_name()}-llm"
