"""
tracker.py — يتتبع حالة كل playlist وكل فيديو
يُحفظ كـ JSON على الديسك ويُقرأ في بداية كل أمر
"""

import json
import os
from pathlib import Path


class Tracker:
    def __init__(self, session: str, base_dir: str = "./data"):
        self.session = session
        self.path = Path(base_dir) / session / "tracker.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        return {"session": self.session, "playlists": {}}

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # ── Playlist ────────────────────────────────────────────

    def is_playlist_downloaded(self, playlist_id: str) -> bool:
        return self.data["playlists"].get(playlist_id, {}).get("downloaded", False)

    def is_playlist_processed(self, playlist_id: str) -> bool:
        return self.data["playlists"].get(playlist_id, {}).get("processed", False)

    def add_playlist(self, playlist_id: str, url: str):
        if playlist_id not in self.data["playlists"]:
            self.data["playlists"][playlist_id] = {
                "url": url,
                "downloaded": False,
                "processed": False,
                "videos": {}
            }
            self._save()

    def mark_playlist_downloaded(self, playlist_id: str):
        self.data["playlists"][playlist_id]["downloaded"] = True
        self._save()
        print(f"  ✔ [tracker] playlist {playlist_id} → downloaded")

    def mark_playlist_processed(self, playlist_id: str):
        self.data["playlists"][playlist_id]["processed"] = True
        self._save()
        print(f"  ✔ [tracker] playlist {playlist_id} → processed")

    # ── Video ───────────────────────────────────────────────

    def is_video_downloaded(self, playlist_id: str, video_id: str) -> bool:
        return (self.data["playlists"]
                .get(playlist_id, {})
                .get("videos", {})
                .get(video_id, {})
                .get("downloaded", False))

    def is_video_processed(self, playlist_id: str, video_id: str) -> bool:
        return (self.data["playlists"]
                .get(playlist_id, {})
                .get("videos", {})
                .get(video_id, {})
                .get("processed", False))

    def mark_video_downloaded(self, playlist_id: str, video_id: str):
        self.data["playlists"][playlist_id]["videos"].setdefault(video_id, {})
        self.data["playlists"][playlist_id]["videos"][video_id]["downloaded"] = True
        self._save()

    def mark_video_processed(self, playlist_id: str, video_id: str):
        self.data["playlists"][playlist_id]["videos"].setdefault(video_id, {})
        self.data["playlists"][playlist_id]["videos"][video_id]["processed"] = True
        self._save()

    # ── Info ────────────────────────────────────────────────

    def summary(self):
        total_pl = len(self.data["playlists"])
        dl_pl = sum(1 for p in self.data["playlists"].values() if p["downloaded"])
        pr_pl = sum(1 for p in self.data["playlists"].values() if p["processed"])
        total_v = sum(len(p["videos"]) for p in self.data["playlists"].values())
        dl_v = sum(
            sum(1 for v in p["videos"].values() if v.get("downloaded"))
            for p in self.data["playlists"].values()
        )
        pr_v = sum(
            sum(1 for v in p["videos"].values() if v.get("processed"))
            for p in self.data["playlists"].values()
        )
        print(f"""
┌─────────────────────────────────────┐
  Session  : {self.session}
  Playlists: {dl_pl}/{total_pl} downloaded  |  {pr_pl}/{total_pl} processed
  Videos   : {dl_v}/{total_v} downloaded  |  {pr_v}/{total_v} processed
└─────────────────────────────────────┘""")

    def get_pending_download(self):
        """إرجاع الـ playlists اللي لم تُحمَّل بعد"""
        return [
            (pid, pdata["url"])
            for pid, pdata in self.data["playlists"].items()
            if not pdata["downloaded"]
        ]

    def get_pending_process(self):
        """إرجاع الـ playlists اللي حُمِّلت ولم تُعالَج بعد"""
        return [
            pid
            for pid, pdata in self.data["playlists"].items()
            if pdata["downloaded"] and not pdata["processed"]
        ]
