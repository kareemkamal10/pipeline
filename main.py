"""
main.py — نقطة التشغيل الرئيسية من CLI

الاستخدام:
  # تحميل (CPU)
  python main.py download --session batch_01 --playlists URL1 URL2

  # معالجة (GPU)
  python main.py process --session batch_01

  # رفع النتائج
  python main.py upload --session batch_01 --dataset history-lab-batch-01

  # عرض حالة الجلسة
  python main.py status --session batch_01
"""

import argparse
import sys


def cmd_download(args):
    from downloader import download_session
    if not args.playlists:
        print("✗ يجب تحديد رابط playlist واحد على الأقل")
        print("  مثال: python main.py download --session batch_01 --playlists URL1 URL2")
        sys.exit(1)
    download_session(args.session, args.playlists, args.data_dir)


def cmd_process(args):
    from processor import process_session
    process_session(args.session, args.data_dir)


def cmd_upload(args):
    from uploader import upload_session
    if not args.dataset:
        print("✗ يجب تحديد اسم الـ Dataset")
        print("  مثال: python main.py upload --session batch_01 --dataset history-lab-batch-01")
        sys.exit(1)
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
    parser.add_argument("--data-dir", default="./data", help="مجلد حفظ البيانات (default: ./data)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── download ──────────────────────────────────────────
    dl = subparsers.add_parser("download", help="تحميل الصوت من YouTube (CPU)")
    dl.add_argument("--session",   required=True, help="اسم الجلسة (مثال: batch_01)")
    dl.add_argument("--playlists", nargs="+",     help="روابط قوائم التشغيل")

    # ── process ───────────────────────────────────────────
    pr = subparsers.add_parser("process", help="تنقية الصوت + النسخ (GPU)")
    pr.add_argument("--session", required=True, help="اسم الجلسة")

    # ── upload ────────────────────────────────────────────
    up = subparsers.add_parser("upload", help="رفع النتائج إلى Kaggle")
    up.add_argument("--session", required=True, help="اسم الجلسة")
    up.add_argument("--dataset", required=True, help="اسم الـ Dataset على Kaggle")

    # ── status ────────────────────────────────────────────
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
