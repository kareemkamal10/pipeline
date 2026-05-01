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

    يدعم الاستئناف: إذا كان الملف معالجاً مسبقاً يتم تجاوزه.
    """
    data_path = Path(base_dir)
    raw_audio_dir = data_path / "raw_audio"

    # إعداد مجلدات الإخراج
    output_dirs = {
        "vocals":        data_path / "vocals",
        "transcripts":   data_path / "transcripts",
        "fulltranscripts": data_path / "fulltranscripts",
        "metadata":      data_path / "metadata",
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

    if device == "cpu":
        print("\n  ⚠️  تحذير: لا يوجد GPU — Demucs وWhisperX سيعملان على CPU وهو بطيء جداً.")
        print("       يُنصح بشدة بالتشغيل على بيئة Lightning.ai مع L40s GPU.")
        print("       للاستمرار على CPU اضغط Enter، أو Ctrl+C للإلغاء.")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            print("\n  ✗ تم الإلغاء.")
            return

    # ── المرحلة الأولى: عزل الصوت (Demucs) لجميع الملفات ──────────────────
    # نفصل Demucs عن WhisperX لتجنب ضغط الذاكرة على GPU

    print("\n━━━━━━━━━━━━━━ المرحلة أ: عزل الصوت (Demucs) ━━━━━━━━━━━━━━")
    isolated_map = {}   # video_id → isolated_wav_path
    demucs_failed = []

    for wav_path in wav_files:
        video_id = wav_path.stem
        isolated_out = output_dirs["vocals"] / f"{video_id}_isolated.wav"

        if isolated_out.exists() and isolated_out.stat().st_size > 0:
            print(f"  ↩ تجاوز Demucs ({video_id}) — الملف موجود مسبقاً")
            isolated_map[video_id] = isolated_out
            continue

        print(f"\n  ▶ عزل الصوت: {video_id}")
        try:
            isolated_map[video_id] = _run_demucs(wav_path, isolated_out)
            print(f"  ✔ انتهى عزل: {video_id}")
        except Exception as e:
            print(f"  ✗ فشل Demucs لـ {video_id}: {e}")
            traceback.print_exc()
            demucs_failed.append(video_id)

    if not isolated_map:
        print("\n✗ لم ينجح عزل أي ملف، يُرجى التحقق من تثبيت Demucs.")
        return

    # ── المرحلة الثانية: تحميل WhisperX ثم التقطيع والتفريغ ─────────────────

    print("\n━━━━━━━━━━━━━━ المرحلة ب: تفريغ النصوص (WhisperX) ━━━━━━━━━━━━━━")
    print("▶ تحميل نماذج WhisperX...")
    whisper_model, align_model, align_meta = _load_whisperx(device, compute_type)
    print("  ✔ تم تحميل النماذج")

    all_metadata_samples = []
    failed_videos = list(demucs_failed)

    for video_id, isolated_audio in isolated_map.items():
        # تحقق هل الفيديو مكتمل مسبقاً (fulltranscript موجود)
        full_text_file = output_dirs["fulltranscripts"] / f"{video_id}.txt"
        if full_text_file.exists() and full_text_file.stat().st_size > 0:
            # أعد تجميع metadata من الملفات الموجودة فقط
            existing = _collect_existing_metadata(video_id, output_dirs, data_path)
            if existing:
                print(f"  ↩ تجاوز التفريغ ({video_id}) — مكتمل مسبقاً ({len(existing)} مقطع)")
                all_metadata_samples.extend(existing)
                continue

        print(f"\n━━━ معالجة: {video_id}")
        t0 = time.time()

        try:
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

                text_file = output_dirs["transcripts"] / f"{video_id}_{idx:03d}.txt"
                with open(text_file, "w", encoding="utf-8") as f:
                    f.write(text)

                full_text.append(text)

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
            with open(full_text_file, "w", encoding="utf-8") as f:
                f.write("\n".join(full_text))

            elapsed = time.time() - t0
            print(f"  ✔ انتهت المعالجة ({len(segment_files)} مقاطع) — {elapsed:.1f}ث")

        except Exception as e:
            print(f"  ✗ فشلت المعالجة: {e}")
            traceback.print_exc()
            failed_videos.append(video_id)

    # ── حفظ metadata الموحد ───────────────────────────────────────────────────

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
    print(f"   - {metadata['total_hours']:.2f} ساعة من الصوت")
    print(f"   - metadata: {metadata_file}")
    if failed_videos:
        print(f"   ⚠ فشلت: {', '.join(failed_videos)}")


# ── دوال مساعدة ─────────────────────────────────────────────


def _collect_existing_metadata(video_id: str, output_dirs: dict, data_path: Path) -> list:
    """جمع metadata من مقاطع مكتملة مسبقاً لتجنب إعادة المعالجة"""
    samples = []
    vocals_dir = output_dirs["vocals"]
    transcripts_dir = output_dirs["transcripts"]

    segment_files = sorted(vocals_dir.glob(f"{video_id}_[0-9]*.wav"))
    for seg_file in segment_files:
        # استخرج index من اسم الملف
        try:
            idx = int(seg_file.stem.split("_")[-1])
        except ValueError:
            continue

        text_file = transcripts_dir / f"{video_id}_{idx:03d}.txt"
        if not text_file.exists():
            continue

        text = text_file.read_text(encoding="utf-8").strip()
        try:
            info = torchaudio.info(str(seg_file))
            duration = info.num_frames / info.sample_rate
        except Exception:
            duration = 0.0

        samples.append({
            "video_id": video_id,
            "segment_id": idx,
            "audio_file": str(seg_file.relative_to(data_path)),
            "text_file": str(text_file.relative_to(data_path)),
            "duration_seconds": round(duration, 2),
            "file_size_bytes": seg_file.stat().st_size,
            "text": text,
        })

    return samples


def _run_demucs(wav_path: Path, out_path: Path) -> Path:
    """عزل الصوت باستخدام Demucs CLI مع إظهار التقدم"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = out_path.parent / f"demucs_tmp_{wav_path.stem}"

    try:
        # لا نستخدم capture_output حتى يظهر تقدم Demucs للمستخدم
        result = subprocess.run([
            "python", "-m", "demucs",
            "--two-stems", "vocals",
            "-n", "htdemucs_ft",
            "--out", str(tmp_dir),
            str(wav_path)
        ], check=True)

        vocal_files = list(tmp_dir.rglob("vocals.wav"))
        if not vocal_files:
            raise FileNotFoundError(f"لم يجد Demucs ملف vocals في {tmp_dir}")

        shutil.move(str(vocal_files[0]), str(out_path))
        return out_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _segment_by_silence(audio_path: Path, sr=44100,
                        top_db=40, hop_length=512,
                        merge_gap_sec=1.5) -> list:
    """
    تقسيم الصوت عند الصمت الطويل فقط.

    المنطق:
    - librosa.effects.split يُرجع فقط المقاطع الصوتية (الصمت مستبعد تلقائياً).
    - نُدمج أي مقطعين متتاليين إذا كان الصمت بينهما أقل من merge_gap_sec
      (صمت قصير = توقف طبيعي بين الكلام، لا نريد قطعه).
    - إذا كان الصمت أطول من merge_gap_sec (مكان موسيقى محذوفة مثلاً)
      → نجعله نقطة قطع ونتجاهل الصمت نفسه تماماً.

    المعاملات:
        top_db      : حساسية كشف الصمت (40 = -40dB مناسب لصوت بعد Demucs)
        merge_gap_sec: الحد الفاصل بالثواني — صمت أقصر → دمج، أطول → قطع
    """
    try:
        y, sr = librosa.load(str(audio_path), sr=sr)

        # استخراج المقاطع الصوتية (بدون الصمت)
        intervals = librosa.effects.split(y, top_db=top_db, hop_length=hop_length)

        if len(intervals) == 0:
            print(f"    ⚠ لم يُكتشف أي صوت في الملف")
            return []

        # دمج المقاطع المتقاربة (الصمت القصير بينها = داخل الكلام)
        merged = []
        current_start, current_end = intervals[0]

        for next_start, next_end in intervals[1:]:
            gap_sec = (next_start - current_end) / sr
            if gap_sec <= merge_gap_sec:
                # صمت قصير → دمج مع المقطع الحالي
                current_end = next_end
            else:
                # صمت طويل → نُغلق المقطع الحالي ونبدأ جديداً
                merged.append((current_start / sr, current_end / sr))
                current_start, current_end = next_start, next_end

        merged.append((current_start / sr, current_end / sr))

        # تجاهل المقاطع القصيرة جداً (أقل من ثانية — ضوضاء متبقية)
        segments = [(s, e) for s, e in merged if e - s >= 1.0]

        if not segments:
            print(f"    ⚠ لم يتبقَّ أي مقطع بعد الفلترة، استخدام Fallback (30ث)")
            duration = len(y) / sr
            segments = [(i * 30, min((i + 1) * 30, duration))
                        for i in range(int(np.ceil(duration / 30)))]

        print(f"    ✔ {len(segments)} مقطع (merge_gap={merge_gap_sec}s)")
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
