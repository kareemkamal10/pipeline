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

def get_playlist_video_ids(playlist_url):
    """
    Returns a list of (video_id, video_url) for the playlist_url using yt_dlp
    """
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True,
        'force_generic_extractor': False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)
        entries = info.get('entries', [])
        videos = []
        for entry in entries:
            vid = entry.get('id')
            url = entry.get('url')
            if vid and url:
                videos.append((vid, f"https://www.youtube.com/watch?v={vid}"))
        return videos

def download_and_convert(video_urls, out_dir="data/raw_audio"):
    import shutil
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
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
    print(f"\n▶ تحميل الصوت فقط في مجلد مؤقت ...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(video_urls)

    # تحويل كل ملف صوتي إلى wav في المجلد النهائي
    print(f"\n▶ تحويل الملفات الصوتية إلى wav ...")
    for audio_file in tmp_dir.iterdir():
        if audio_file.suffix.lower() in [".wav"]:
            shutil.copy2(audio_file, out_dir / audio_file.name)
            continue
        wav_file = out_dir / f"{audio_file.stem}.wav"
        print(f"  تحويل {audio_file.name} → {wav_file.name}")
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", str(audio_file), "-ar", "44100", "-ac", "1", str(wav_file)
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

    for playlist_url, excludes in all_links:
        print(f"\n=== معالجة قائمة التشغيل: {playlist_url}")
        videos = get_playlist_video_ids(playlist_url)
        found_ids = set(vid for vid, _ in videos)

        for ex in excludes:
            if ex not in found_ids:
                print(f"  ⚠️ لم يتم العثور على الفيديو المستثنى: {ex}")

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
