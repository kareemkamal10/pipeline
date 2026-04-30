"""
processor.py — المرحلة الثانية (GPU)
Demucs vocal isolation + WhisperX transcription
"""

import json
import shutil
import subprocess
import time
import traceback
from pathlib import Path

import torch

from tracker import Tracker


def process_session(session: str, base_dir: str = "./data"):
    tracker = Tracker(session, base_dir)

    audio_dir  = Path(base_dir) / session / "raw_audio"
    vocals_dir = Path(base_dir) / session / "vocals"
    trans_dir  = Path(base_dir) / session / "transcripts"
    vocals_dir.mkdir(parents=True, exist_ok=True)
    trans_dir.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"\n▶ Session: {session}")
    print(f"  Device: {device} | Compute: {compute_type}")

    pending = tracker.get_pending_process()
    if not pending:
        print("\n✔ No playlists ready for processing.")
        tracker.summary()
        return

    print(f"  Pending process: {len(pending)} playlist(s)")

    # تحميل نماذج WhisperX مرة واحدة
    print("\n▶ Loading WhisperX models...")
    whisper_model, align_model, align_meta = _load_whisperx(device, compute_type)
    print("  ✔ Models loaded")

    for playlist_id in pending:
        pl_audio_dir = audio_dir / playlist_id
        wav_files    = sorted(pl_audio_dir.glob("*.wav"))
        print(f"\n━━━ Processing playlist: {playlist_id} ({len(wav_files)} files)")

        failed = 0

        for wav_path in wav_files:
            video_id = wav_path.stem

            if tracker.is_video_processed(playlist_id, video_id):
                print(f"  ⏭ Skip: {video_id}")
                continue

            print(f"\n  🎙 {video_id}")
            t0 = time.time()

            try:
                # ── Step 1: Demucs via CLI (يدعم الملفات الطويلة) ──
                vocals_path = vocals_dir / f"{video_id}.wav"
                if not vocals_path.exists():
                    print(f"    ▶ Demucs...")
                    _run_demucs(wav_path, vocals_path)

                # ── Step 2: WhisperX ────────────────────────────────
                json_out = trans_dir / f"{video_id}.json"
                txt_out  = trans_dir / f"{video_id}.txt"

                if not json_out.exists():
                    print(f"    ▶ WhisperX...")
                    import whisperx

                    audio = whisperx.load_audio(str(vocals_path))

                    result = whisper_model.transcribe(
                        audio,
                        batch_size=16,
                        language="ar",
                        vad_filter=True,
                        vad_parameters={
                            "min_silence_duration_ms": 500,
                            "speech_pad_ms": 400,
                        },
                    )

                    print(f"    ▶ Aligning {len(result['segments'])} segments...")
                    result_aligned = whisperx.align(
                        result["segments"],
                        align_model, align_meta,
                        audio, device,
                        return_char_alignments=False,
                    )

                    # حفظ JSON (word-level timestamps)
                    with open(json_out, "w", encoding="utf-8") as f:
                        json.dump(result_aligned, f, ensure_ascii=False, indent=2)

                    # حفظ TXT (النص الكامل)
                    full_text = " ".join(
                        s.get("text", "").strip()
                        for s in result_aligned.get("segments", [])
                    )
                    with open(txt_out, "w", encoding="utf-8") as f:
                        f.write(full_text)

                    print(f"    ✔ Saved JSON + TXT ({len(full_text.split())} words)")

                tracker.mark_video_processed(playlist_id, video_id)
                elapsed = time.time() - t0
                print(f"    ✔ Done in {elapsed:.1f}s")

            except Exception:
                # FIX: طباعة الـ error الكامل بدلاً من إخفائه
                print(f"    ✗ FAILED: {video_id}")
                traceback.print_exc()
                failed += 1

        # FIX: نضع playlist كـ processed فقط لو كل الملفات نجحت
        if failed == 0:
            tracker.mark_playlist_processed(playlist_id)
            print(f"\n  ✔ Playlist {playlist_id} fully processed")
        else:
            print(f"\n  ⚠ Playlist {playlist_id} had {failed} failed files — will retry on next run")

    tracker.summary()
    print("\n✔ Processing complete — run: upload")


# ── Helpers ─────────────────────────────────────────────────

def _run_demucs(wav_path: Path, out_path: Path):
    """
    FIX: استخدام Demucs CLI بدلاً من apply_model مباشرة
    يدعم الملفات الطويلة تلقائياً بالـ chunking
    """
    tmp_dir = out_path.parent / f"demucs_tmp_{wav_path.stem}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run([
            "python", "-m", "demucs",
            "--two-stems", "vocals",
            "-n", "htdemucs_ft",
            "--out", str(tmp_dir),
            str(wav_path)
        ], check=True)

        # Demucs يحفظ هنا: tmp_dir/htdemucs_ft/FILENAME/vocals.wav
        vocal_files = list(tmp_dir.rglob("vocals.wav"))
        if not vocal_files:
            raise FileNotFoundError(f"Demucs output not found in {tmp_dir}")

        shutil.move(str(vocal_files[0]), str(out_path))
        print(f"    ✔ Vocals saved: {out_path.name}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _load_whisperx(device, compute_type):
    import whisperx
    model = whisperx.load_model(
        "large-v3", device, compute_type=compute_type, language="ar"
    )
    align_model, align_meta = whisperx.load_align_model(
        language_code="ar", device=device
    )
    return model, align_model, align_meta
