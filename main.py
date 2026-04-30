"""
main.py — نقطة التشغيل الرئيسية من CLI

الاستخدام:
  # تحميل (CPU) — الروابط من ملف playlists_urls.txt
  python main.py download --session batch_01

  # معالجة (GPU)
  python main.py process --session batch_01

  # رفع النتائج
  python main.py upload --session batch_01 --dataset history-lab-batch-01

  # عرض حالة الجلسة
  python main.py status --session batch_01

صيغة ملف playlists_urls.txt:
  # هذا تعليق — يتم تجاهله
  https://www.youtube.com/playlist?list=XXX
  https://www.youtube.com/playlist?list=YYY
"""

import argparse
import sys
from pathlib import Path


def load_urls(urls_file: str) -> list:
    path = Path(urls_file)
    if not path.exists():
        print(f"✗ ملف الروابط غير موجود: {urls_file}")
        print(f"\n  أنشئ الملف وضع كل رابط في سطر:")
        print(f"  echo 'https://youtube.com/playlist?list=XXX' >> {urls_file}")
        sys.exit(1)

    urls = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not urls:
        print(f"✗ الملف {urls_file} فارغ — أضف روابط الـ playlists")
        sys.exit(1)

    print(f"  ✔ {len(urls)} رابط من ملف {urls_file}")
    return urls


def cmd_download(args):
    from downloader import download_session
    urls = load_urls(args.urls_file)
    download_session(args.session, urls, args.data_dir)


def cmd_process(args):
    from processor import process_session
    process_session(args.session, args.data_dir)


def cmd_upload(args):
    from uploader import upload_session
    upload_session(args.session, args.dataset, args.data_dir)


def cmd_status(args):
    from tracker import Tracker
    tracker = Tracker(args.session, args.data_dir)
    tracker.summary()


def main():
    parser = argparse.ArgumentParser(
        prog="history-lab",
        description="History Lab Pipeline — Audio Download, Vocal Isolation & Transcription"
    )
    parser.add_argument(
        "--data-dir", default="./data",
        help="مجلد حفظ البيانات (default: ./data)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # download
    dl = subparsers.add_parser("download", help="تحميل الصوت من YouTube (CPU)")
    dl.add_argument("--session",   required=True, help="اسم الجلسة (مثال: batch_01)")
    dl.add_argument(
        "--urls-file", default="playlists_urls.txt",
        help="ملف الروابط (default: playlists_urls.txt)"
    )

    # process
    pr = subparsers.add_parser("process", help="تنقية الصوت + النسخ (GPU)")
    pr.add_argument("--session", required=True, help="اسم الجلسة")

    # upload
    up = subparsers.add_parser("upload", help="رفع النتائج إلى Kaggle")
    up.add_argument("--session",  required=True, help="اسم الجلسة")
    up.add_argument("--dataset",  required=True, help="اسم الـ Dataset على Kaggle")

    # status
    st = subparsers.add_parser("status", help="عرض حالة الجلسة")
    st.add_argument("--session", required=True, help="اسم الجلسة")

    args = parser.parse_args()

    commands = {
        "download": cmd_download,
        "process":  cmd_process,
        "upload":   cmd_upload,
        "status":   cmd_status,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
