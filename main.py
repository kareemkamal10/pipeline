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

    # ── test ─────────────────────────────────────────────
    ts = subparsers.add_parser("test", help="اختبار على فيديو واحد عشوائي")
    ts.add_argument("--session", required=True, help="اسم الجلسة")

    args = parser.parse_args()

    commands = {
        "download": cmd_download,
        "process":  cmd_process,
        "upload":   cmd_upload,
        "status":   cmd_status,
        "test":     cmd_test,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()


def cmd_test(args):
    """اختبار على فيديو واحد عشوائي"""
    import random
    import torchaudio
    from pathlib import Path
    from processor import _run_demucs, _load_whisperx
    import torch, json, traceback

    # إيجاد ملف عشوائي
    wav_files = list(Path(args.data_dir, args.session, "raw_audio").rglob("*.wav"))
    if not wav_files:
        print("✗ No audio files found — run download first")
        return

    wav_path = random.choice(wav_files)
    info = torchaudio.info(str(wav_path))
    duration = info.num_frames / info.sample_rate / 60
    print(f"\n🎲 Random test file: {wav_path.name}")
    print(f"   Duration: {duration:.1f} min")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"   Device: {device}\n")

    # مجلدات مؤقتة للاختبار
    test_dir = Path(args.data_dir) / args.session / "test_output"
    test_dir.mkdir(parents=True, exist_ok=True)
    vocals_path = test_dir / f"{wav_path.stem}_vocals.wav"
    json_out    = test_dir / f"{wav_path.stem}.json"
    txt_out     = test_dir / f"{wav_path.stem}.txt"

    try:
        # Step 1: Demucs
        print("▶ Step 1: Demucs vocal isolation...")
        _run_demucs(wav_path, vocals_path)
        v_info = torchaudio.info(str(vocals_path))
        v_dur  = v_info.num_frames / v_info.sample_rate / 60
        print(f"  ✔ Vocals: {v_dur:.1f} min (original: {duration:.1f} min)")

        if abs(v_dur - duration) > 0.5:
            print(f"  ⚠ WARNING: duration mismatch! possible truncation")

        # Step 2: WhisperX
        print("\n▶ Step 2: WhisperX transcription...")
        import whisperx
        whisper_model, align_model, align_meta = _load_whisperx(device, compute_type)
        audio = whisperx.load_audio(str(vocals_path))

        result = whisper_model.transcribe(
            audio, batch_size=16, language="ar",
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 400},
        )
        print(f"  ✔ Transcribed: {len(result['segments'])} segments")

        result_aligned = whisperx.align(
            result["segments"], align_model, align_meta, audio, device,
            return_char_alignments=False,
        )

        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(result_aligned, f, ensure_ascii=False, indent=2)

        full_text = " ".join(
            s.get("text", "").strip()
            for s in result_aligned.get("segments", [])
        )
        with open(txt_out, "w", encoding="utf-8") as f:
            f.write(full_text)

        print(f"  ✔ Saved: {json_out.name} + {txt_out.name}")
        print(f"  ✔ Words: {len(full_text.split())}")
        print(f"\n  📝 Sample text (first 200 chars):")
        print(f"  {full_text[:200]}")
        print(f"\n✅ TEST PASSED — pipeline is working correctly!")

    except Exception:
        print("\n❌ TEST FAILED:")
        traceback.print_exc()
