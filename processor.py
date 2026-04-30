"""
processor.py — المرحلة الثانية (GPU)
Demucs vocal isolation + WhisperX transcription
"""

import os
import json
import time
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

    # تحميل النماذج مرة واحدة
    print("\n▶ Loading models...")
    demucs_model  = _load_demucs(device)
    whisper_model, align_model, align_meta = _load_whisperx(device, compute_type)
    print("  ✔ Models loaded")

    for playlist_id in pending:
        pl_audio_dir = audio_dir / playlist_id
        wav_files    = sorted(pl_audio_dir.glob("*.wav"))
        print(f"\n━━━ Processing playlist: {playlist_id} ({len(wav_files)} files)")

        for wav_path in wav_files:
            video_id = wav_path.stem

            if tracker.is_video_processed(playlist_id, video_id):
                print(f"  ⏭ Skip: {video_id}")
                continue

            print(f"  🎙 {video_id}")
            t0 = time.time()

            try:
                # ── Step 1: Demucs vocal isolation ─────────
                vocals_path = vocals_dir / f"{video_id}.wav"
                if not vocals_path.exists():
                    _run_demucs(demucs_model, wav_path, vocals_path, device)

                # ── Step 2: WhisperX transcription ─────────
                json_out = trans_dir / f"{video_id}.json"
                txt_out  = trans_dir / f"{video_id}.txt"

                if not json_out.exists():
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

                    result_aligned = whisperx.align(
                        result["segments"],
                        align_model, align_meta,
                        audio, device,
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

                tracker.mark_video_processed(playlist_id, video_id)

                elapsed = time.time() - t0
                print(f"    ✔ {elapsed:.1f}s")

            except Exception as e:
                print(f"    ✗ Error: {e}")

        tracker.mark_playlist_processed(playlist_id)

    tracker.summary()
    print("\n✔ Processing complete — run: upload")


# ── Helpers ─────────────────────────────────────────────────

def _load_demucs(device):
    from demucs.pretrained import get_model
    model = get_model("htdemucs_ft")
    model.to(device)
    model.eval()
    return model


def _run_demucs(model, wav_path: Path, out_path: Path, device: str):
    import torchaudio
    from demucs.apply import apply_model
    from demucs.audio import save_audio

    wav, sr = torchaudio.load(str(wav_path))
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    wav = wav.unsqueeze(0).to(device)

    with torch.no_grad():
        sources = apply_model(model, wav, device=device)[0]

    vocals = sources[3].mean(0, keepdim=True).cpu()
    save_audio(vocals, str(out_path), samplerate=sr)


def _load_whisperx(device, compute_type):
    import whisperx
    model = whisperx.load_model(
        "large-v3", device, compute_type=compute_type, language="ar"
    )
    align_model, align_meta = whisperx.load_align_model(
        language_code="ar", device=device
    )
    return model, align_model, align_meta
