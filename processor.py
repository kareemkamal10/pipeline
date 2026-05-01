"""
processor.py — المرحلة الثانية (GPU)
عزل الصوت + تقسيم عند التوقفات + تفريغ + إنشاء metadata موحد
"""

import json
import shutil
import subprocess
import time
import traceback
from pathlib import Path

import torch
import torchaudio
import librosa
import numpy as np


def process_session(base_dir: str = "data"):
    """
    معالجة جميع الملفات الخام في data/raw_audio/:
    1. عزل الصوت (Demucs)
    2. تقسيم عند التوقفات
    3. تفريغ المقاطع (WhisperX)
    4. إنشاء metadata موحد للجلسة كاملة
    """
    data_path = Path(base_dir)
    raw_audio_dir = data_path / "raw_audio"
    
    # إعداد مجلدات الإخراج
    output_dirs = {
        "vocals": data_path / "vocals",
        "transcripts": data_path / "transcripts",
        "fulltranscripts": data_path / "fulltranscripts",
        "metadata": data_path / "metadata",
    }
    
    for dir_path in output_dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)
    
    if not raw_audio_dir.exists():
        print(f"✗ مجلد raw_audio/ غير موجود في {data_path}")
        return
    
    wav_files = sorted(raw_audio_dir.glob("*.wav"))
    if not wav_files:
        print("✗ لم يتم العثور على ملفات WAV في raw_audio/")
        return
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"\n▶ المعالجة")
    print(f"  Device: {device} | Compute: {compute_type}")
    print(f"  ملفات للمعالجة: {len(wav_files)}")
    
    # تحميل نماذج WhisperX مرة واحدة
    print("\n▶ تحميل نماذج WhisperX...")
    whisper_model, align_model, align_meta = _load_whisperx(device, compute_type)
    print("  ✔ تم تحميل النماذج")
    
    all_metadata_samples = []
    failed_videos = []
    
    for wav_path in wav_files:
        video_id = wav_path.stem
        print(f"\n━━━ معالجة: {video_id}")
        t0 = time.time()
        
        try:
            # الخطوة 1: عزل الصوت
            print(f"  ▶ عزل الصوت (Demucs)...")
            isolated_audio = _run_demucs(wav_path, output_dirs["vocals"] / f"{video_id}_isolated.wav")
            
            # الخطوة 2: تقسيم عند التوقفات
            print(f"  ▶ تقسيم الصوت عند التوقفات...")
            segments = _segment_by_silence(isolated_audio)
            if not segments:
                print(f"  ⚠ لم يتم العثور على مقاطع صوتية")
                failed_videos.append(video_id)
                continue
            
            # الخطوة 3: استخراج المقاطع
            print(f"  ▶ استخراج المقاطع...")
            segment_files = _extract_segments(isolated_audio, segments, output_dirs["vocals"], video_id)
            
            # الخطوة 4: تفريغ النصوص
            print(f"  ▶ تفريغ المقاطع (WhisperX)...")
            transcriptions = _transcribe_segments(segment_files, whisper_model, align_model, align_meta, device)
            
            # الخطوة 5: حفظ النصوص والـ metadata
            full_text = []
            for idx, segment_file, start_sec, end_sec in segment_files:
                text = transcriptions.get(idx, {}).get("text", "")
                
                # حفظ النص لكل مقطع
                text_file = output_dirs["transcripts"] / f"{video_id}_{idx:03d}.txt"
                with open(text_file, "w", encoding="utf-8") as f:
                    f.write(text)
                
                full_text.append(text)
                
                # جمع معلومات metadata
                file_size = segment_file.stat().st_size
                duration = end_sec - start_sec
                all_metadata_samples.append({
                    "video_id": video_id,
                    "segment_id": idx,
                    "audio_file": str(segment_file.relative_to(data_path)),
                    "text_file": str(text_file.relative_to(data_path)),
                    "duration_seconds": round(duration, 2),
                    "file_size_bytes": file_size,
                    "text": text,
                })
            
            # حفظ النص الكامل
            full_text_file = output_dirs["fulltranscripts"] / f"{video_id}.txt"
            with open(full_text_file, "w", encoding="utf-8") as f:
                f.write("\n".join(full_text))
            
            elapsed = time.time() - t0
            print(f"  ✔ انتهت المعالجة ({len(segment_files)} مقاطع) — {elapsed:.1f}ث")
            
        except Exception as e:
            print(f"  ✗ فشلت المعالجة: {e}")
            traceback.print_exc()
            failed_videos.append(video_id)
    
    # حفظ metadata الموحد
    metadata_file = output_dirs["metadata"] / "tts_metadata.json"
    total_duration = sum(s["duration_seconds"] for s in all_metadata_samples)
    metadata = {
        "dataset_name": "history_lab_tts",
        "total_samples": len(all_metadata_samples),
        "total_hours": round(total_duration / 3600, 2),
        "samples": all_metadata_samples,
    }
    
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    print(f"\n✔ اكتملت المعالجة!")
    print(f"   الملفات المنتجة:")
    print(f"   - {len(all_metadata_samples)} مقطع صوتي/نصي")
    print(f"   - {metadata['total_hours']:.1f} ساعة من الصوت")
    print(f"   - metadata: {metadata_file}")
    if failed_videos:
        print(f"   ⚠ فشلت: {', '.join(failed_videos)}")


# ── دوال مساعدة ─────────────────────────────────────────────


def _run_demucs(wav_path: Path, out_path: Path) -> Path:
    """عزل الصوت باستخدام Demucs CLI"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = out_path.parent / f"demucs_tmp_{wav_path.stem}"
    
    try:
        subprocess.run([
            "python", "-m", "demucs",
            "--two-stems", "vocals",
            "-n", "htdemucs_ft",
            "--out", str(tmp_dir),
            str(wav_path)
        ], check=True, capture_output=True)
        
        vocal_files = list(tmp_dir.rglob("vocals.wav"))
        if not vocal_files:
            raise FileNotFoundError(f"لم يجد Demucs صوت في {tmp_dir}")
        
        shutil.move(str(vocal_files[0]), str(out_path))
        return out_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _segment_by_silence(audio_path: Path, min_silence_duration=0.5, sr=44100) -> list:
    """تقسيم الصوت عند التوقفات (الصمت)"""
    try:
        y, sr = librosa.load(str(audio_path), sr=sr)

        # Use a fixed hop_length to avoid relying on removed internals
        hop_length = 512

        # Use librosa.effects.split to get non-silent intervals (speech)
        # top_db controls sensitivity; 40 ~= -40dB threshold
        intervals = librosa.effects.split(y, top_db=40, hop_length=hop_length)

        segments = []
        for start_sample, end_sample in intervals:
            start_sec = start_sample / sr
            end_sec = end_sample / sr
            # skip too-short segments
            if end_sec - start_sec < 0.3:
                continue
            segments.append((start_sec, end_sec))

        # If no segments detected, fallback to fixed-size chunks
        if not segments:
            duration = len(y) / sr
            segment_length = 30
            segments = [(i * segment_length, min((i+1) * segment_length, duration))
                       for i in range(int(np.ceil(duration / segment_length)))]

        return segments
    except Exception as e:
        print(f"  ✗ فشل التقسيم: {e}")
        return []


def _extract_segments(audio_path: Path, segments: list, output_dir: Path, video_id: str) -> list:
    """استخراج المقاطع الصوتية الصغيرة"""
    output_dir.mkdir(parents=True, exist_ok=True)
    y, sr = librosa.load(str(audio_path), sr=44100)
    segment_files = []
    
    for idx, (start_sec, end_sec) in enumerate(segments):
        start_sample = int(start_sec * sr)
        end_sample = int(end_sec * sr)
        segment_audio = y[start_sample:end_sample]
        
        if len(segment_audio) < sr * 0.3:
            continue
        
        segment_file = output_dir / f"{video_id}_{idx:03d}.wav"
        torchaudio.save(str(segment_file), torch.from_numpy(segment_audio).unsqueeze(0), sr)
        segment_files.append((idx, segment_file, start_sec, end_sec))
    
    print(f"    ✔ استخرج {len(segment_files)} مقطع")
    return segment_files


def _transcribe_segments(segment_files: list, whisper_model, align_model, align_meta, device: str) -> dict:
    """تفريغ المقاطع باستخدام WhisperX"""
    import whisperx
    transcriptions = {}
    
    for idx, segment_file, start_sec, end_sec in segment_files:
        try:
            audio = whisperx.load_audio(str(segment_file))
            result = whisper_model.transcribe(audio, language="ar")
            result = whisperx.align(
                result["segments"],
                align_model,
                align_meta,
                audio,
                device,
                return_char_alignments=False,
            )
            text = " ".join(s.get("text", "").strip() for s in result.get("segments", []))
            transcriptions[idx] = {"text": text, "start": start_sec, "end": end_sec}
        except Exception as e:
            print(f"    ⚠ فشل تفريغ مقطع {idx}: {e}")
            transcriptions[idx] = {"text": "", "start": start_sec, "end": end_sec}
    
    return transcriptions


def _load_whisperx(device, compute_type):
    """تحميل نماذج WhisperX"""
    import whisperx
    model = whisperx.load_model(
        "large-v3", device, compute_type=compute_type, language="ar"
    )
    align_model, align_meta = whisperx.load_align_model(
        language_code="ar", device=device
    )
    return model, align_model, align_meta
