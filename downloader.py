"""
downloader.py — المرحلة الأولى (CPU)
تحميل قوائم التشغيل كـ WAV 44100Hz وحفظها على الديسك
"""

import os
import re
from pathlib import Path

import yt_dlp

from tracker import Tracker


def extract_playlist_id(url: str) -> str:
    """استخراج playlist ID من الرابط"""
    match = re.search(r"list=([A-Za-z0-9_-]+)", url)
    if match:
        return match.group(1)
    # رابط فيديو عادي — نعامله كـ playlist ID = video ID
    match = re.search(r"v=([A-Za-z0-9_-]+)", url)
    if match:
        return match.group(1)
    # إذا مفيش pattern واضح — نستخدم الرابط كـ ID مختصر
    return re.sub(r"[^A-Za-z0-9_-]", "_", url)[-32:]


def download_session(session: str, playlist_urls: list[str], base_dir: str = "./data"):
    tracker = Tracker(session, base_dir)
    audio_dir = Path(base_dir) / session / "raw_audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n▶ Session: {session}")
    print(f"  Playlists received: {len(playlist_urls)}")

    # تسجيل الـ playlists في الـ tracker
    for url in playlist_urls:
        pid = extract_playlist_id(url)
        tracker.add_playlist(pid, url)

    # فحص ما تم تحميله بالفعل
    pending = tracker.get_pending_download()
    if not pending:
        print("\n✔ All playlists already downloaded — nothing to do.")
        tracker.summary()
        return

    print(f"  Pending download: {len(pending)} playlist(s)\n")

    for playlist_id, url in pending:
        print(f"\n━━━ Downloading playlist: {playlist_id}")
        print(f"  URL: {url}")

        # مسار خاص بكل playlist
        pl_dir = audio_dir / playlist_id
        pl_dir.mkdir(parents=True, exist_ok=True)

        downloaded_ids = []

        def progress_hook(d):
            if d["status"] == "finished":
                vid_id = Path(d["filename"]).stem
                tracker.mark_video_downloaded(playlist_id, vid_id)
                downloaded_ids.append(vid_id)

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(pl_dir / "%(id)s.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "0",
            }],
            "postprocessor_args": [
                "-ar", "44100",
                "-ac", "1",
            ],
            "ignoreerrors": True,
            "quiet": False,
            "progress_hooks": [progress_hook],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            tracker.mark_playlist_downloaded(playlist_id)
            print(f"  ✔ Playlist done — {len(downloaded_ids)} videos")

        except Exception as e:
            print(f"  ✗ Error on playlist {playlist_id}: {e}")

    tracker.summary()
    print("\n✔ Download stage complete — switch to GPU and run: process")
