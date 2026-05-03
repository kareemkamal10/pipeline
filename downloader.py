import os
import sys
import csv
import subprocess
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    print("يرجى تثبيت yt-dlp: pip install yt-dlp")
    sys.exit(1)

def read_links_and_excludes(csv_path):
    """
    Reads playLinks.csv and returns a list of (playlist_url, set_of_excluded_video_ids)
    """
    result = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[0].strip() or row[0].strip().startswith('#'):
                continue
            url = row[0].strip()
            excludes = set(x.strip() for x in row[1:] if x.strip())
            result.append((url, excludes))
    return result

def _is_single_video(url: str) -> bool:
    """هل الرابط فيديو مفرد أم قائمة تشغيل؟"""
    return (
        ("watch?v=" in url or "youtu.be/" in url)
        and "list=" not in url
    )


def _extract_video_id(url: str):
    """استخراج video_id من رابط فيديو مفرد"""
    if "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0].strip()
    if "watch?v=" in url:
        return url.split("watch?v=")[-1].split("&")[0].strip()
    return None


def get_playlist_video_ids(url, exclude_ids=None):
    """
    استخراج الفيديوهات من:
    - قائمة تشغيل كاملة  (playlist?list=...)
    - فيديو مفرد         (watch?v=... أو youtu.be/...)
    مع استثناء المحددة في exclude_ids
    """
    if exclude_ids is None:
        exclude_ids = set()

    # ── فيديو مفرد ───────────────────────────────────────────
    if _is_single_video(url):
        vid = _extract_video_id(url)
        if not vid:
            print(f"  ✗ لم يتم استخراج video_id من: {url}")
            return []
        if vid in exclude_ids:
            print(f"  ↩ فيديو مستثنى: {vid}")
            return []
        print(f"  ✔ فيديو مفرد: {vid}")
        return [(vid, f"https://www.youtube.com/watch?v={vid}")]

    # ── قائمة تشغيل ──────────────────────────────────────────
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True,
        'force_generic_extractor': False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        entries = info.get('entries', [])
        videos = []
        for entry in entries:
            vid = entry.get('id')
            if vid and vid not in exclude_ids:
                videos.append((vid, f"https://www.youtube.com/watch?v={vid}"))
        return videos

def download_and_convert(video_urls, out_dir="data/raw_audio"):
    import shutil
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # تصفية الفيديوهات المحملة مسبقاً
    urls_to_download = []
    for url in video_urls:
        vid_id = url.split("v=")[-1].split("&")[0] if "v=" in url else None
        if vid_id:
            existing = out_dir / f"{vid_id}.wav"
            if existing.exists() and existing.stat().st_size > 0:
                print(f"  ↩ تجاوز التحميل ({vid_id}) — الملف موجود مسبقاً")
                continue
        urls_to_download.append(url)

    if not urls_to_download:
        print("  ✔ جميع الملفات محملة مسبقاً، لا يوجد شيء جديد.")
        return

    tmp_dir = Path("./_tmp_download")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # تحميل الصوت فقط في مجلد مؤقت
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(tmp_dir / "%(id)s.%(ext)s"),
        "ignoreerrors": True,
        "quiet": False,
    }
    print(f"\n▶ تحميل {len(urls_to_download)} فيديو في مجلد مؤقت ...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(urls_to_download)

    # تحويل كل ملف صوتي إلى wav في المجلد النهائي
    print(f"\n▶ تحويل الملفات الصوتية إلى wav ...")
    for audio_file in tmp_dir.iterdir():
        if audio_file.suffix.lower() == ".wav":
            shutil.copy2(audio_file, out_dir / audio_file.name)
            continue
        wav_file = out_dir / f"{audio_file.stem}.wav"
        print(f"  تحويل {audio_file.name} → {wav_file.name}")
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", str(audio_file),
                "-ar", "44100", "-ac", "1", str(wav_file)
            ], check=True)
        except Exception as e:
            print(f"  ✗ فشل التحويل: {e}")
    shutil.rmtree(tmp_dir)
    print("\n✔ انتهى! ستجد ملفات wav فقط في:", out_dir)

def download_from_csv(csv_path, out_dir="data/raw_audio"):
    """Read playLinks.csv, apply exclusions, and download all playlists."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        print(f"✗ ملف {csv_path} غير موجود!")
        return

    all_links = read_links_and_excludes(csv_path)
    if not all_links:
        print("✗ لم يتم العثور على روابط في الملف!")
        return

    for url, excludes in all_links:
        label = "فيديو مفرد" if _is_single_video(url) else "قائمة تشغيل"
        print(f"\n=== معالجة {label}: {url}")
        videos = get_playlist_video_ids(url, exclude_ids=excludes)

        filtered = [(vid, url) for vid, url in videos if vid not in excludes]
        if not filtered:
            print("  لا يوجد فيديوهات متاحة بعد الاستثناءات!")
            continue

        print(f"  سيتم تحميل {len(filtered)} فيديو...")
        video_urls = [url for _, url in filtered]
        download_and_convert(video_urls, out_dir)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("استخدم: python downloader.py playLinks.csv")
        sys.exit(1)
    csv_path = sys.argv[1]
    download_from_csv(csv_path, Path("data") / "raw_audio")
