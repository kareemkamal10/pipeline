"""
main.py — نقطة التشغيل الرئيسية من CLI

الاستخدام:

🔴 المرحلة 1 — التحميل (CPU):
  python main.py download playLinks.csv
  
  (يقرأ playLinks.csv بالشكل: link,videoId1,videoId2,...)
  (يحمل الملفات في data/raw_audio/)

🟢 المرحلة 2 — المعالجة (GPU):
  python main.py process
  
  (يعزل الصوت + يقسم عند التوقفات + يفرغ النصوص)
  (الناتج: vocals/ + transcripts/ + fulltranscripts/ + metadata/)

🔵 المرحلة 3 — الرفع (Kaggle):
  python main.py upload
  
  (يرفع TTS Dataset + LLM Dataset حسب config.yaml)
"""

import argparse
import sys
from pathlib import Path


def cmd_download(args):
    """تحميل الملفات من YouTube"""
    from downloader import download_from_csv
    csv_path = Path(args.csv_file)
    print("▶ المرحلة 1: download فقط")
    print(f"  CWD: {Path.cwd()}")
    print(f"  CSV: {csv_path.resolve() if csv_path.exists() else csv_path}")
    download_from_csv(csv_path)


def cmd_process(args):
    """معالجة الملفات (عزل + تقسيم + تفريغ)"""
    from processor import process_session
    process_session(data_dir="data")


def cmd_upload(args):
    """رفع Datasets إلى Kaggle"""
    from uploader import upload_datasets
    upload_datasets(config_path="config.yaml", data_dir="data")


def main():
    parser = argparse.ArgumentParser(
        prog="history-lab",
        description="History Lab Pipeline — تحميل، معالجة، ورفع الصوت الخام"
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    # download
    dl = subparsers.add_parser("download", help="🔴 المرحلة 1: تحميل من YouTube (CPU)")
    dl.add_argument("csv_file", help="ملف playLinks.csv (شكل: link,videoId1,videoId2,...)")

    # process
    pr = subparsers.add_parser("process", help="🟢 المرحلة 2: معالجة الملفات (GPU)")

    # upload
    up = subparsers.add_parser("upload", help="🔵 المرحلة 3: رفع إلى Kaggle")

    args = parser.parse_args()

    commands = {
        "download": cmd_download,
        "process": cmd_process,
        "upload": cmd_upload,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
