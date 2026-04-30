"""
uploader.py — رفع نتائج الجلسة إلى Kaggle Dataset
كل جلسة → Dataset مستقل باسمها
"""

import json
import os
import subprocess
from pathlib import Path

from tracker import Tracker


def upload_session(session: str, dataset_name: str, base_dir: str = "./data"):
    tracker = Tracker(session, base_dir)
    session_dir = Path(base_dir) / session

    print(f"\n▶ Uploading session: {session}")
    print(f"  Dataset name: {dataset_name}")

    # التحقق من وجود بيانات للرفع
    vocals_dir = session_dir / "vocals"
    trans_dir  = session_dir / "transcripts"

    vocals = list(vocals_dir.glob("*.wav"))  if vocals_dir.exists() else []
    jsons  = list(trans_dir.glob("*.json")) if trans_dir.exists() else []
    txts   = list(trans_dir.glob("*.txt"))  if trans_dir.exists() else []

    print(f"  Vocals  : {len(vocals)} files")
    print(f"  JSON    : {len(jsons)} files")
    print(f"  TXT     : {len(txts)} files")

    if not (vocals or jsons):
        print("  ✗ Nothing to upload.")
        return

    # إنشاء dataset-metadata.json
    kaggle_username = _get_kaggle_username()
    meta = {
        "title": dataset_name,
        "id": f"{kaggle_username}/{dataset_name}",
        "licenses": [{"name": "CC0-1.0"}],
        "keywords": ["arabic", "audio", "transcription", "history-lab"]
    }
    meta_path = session_dir / "dataset-metadata.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    # رفع إلى Kaggle
    print("\n▶ Uploading to Kaggle...")
    try:
        result = subprocess.run(
            f"kaggle datasets create -p {session_dir} --dir-mode zip",
            shell=True, capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  ✔ Dataset created!")
            print(f"  → kaggle.com/datasets/{kaggle_username}/{dataset_name}")
        else:
            # ربما الـ dataset موجود بالفعل — نحدثه
            result2 = subprocess.run(
                f"kaggle datasets version -p {session_dir} -m 'session {session}' --dir-mode zip",
                shell=True, capture_output=True, text=True
            )
            if result2.returncode == 0:
                print(f"  ✔ Dataset version updated!")
            else:
                print(f"  ✗ Kaggle error: {result.stderr}")
    except Exception as e:
        print(f"  ✗ Upload failed: {e}")

    tracker.summary()


def _get_kaggle_username() -> str:
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if kaggle_json.exists():
        with open(kaggle_json) as f:
            return json.load(f)["username"]
    return os.getenv("KAGGLE_USERNAME", "unknown")
