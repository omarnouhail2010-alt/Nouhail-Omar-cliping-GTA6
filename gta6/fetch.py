"""Récupération des vidéos sources, avec contrôle des droits.

Sources acceptées :
  - un fichier local ou un dossier local
  - un lien Google Drive (fichier ou dossier partagé « Tous les utilisateurs disposant du lien »)
  - une URL vidéo (YouTube…) via yt-dlp : uniquement si la licence est Creative Commons,
    ou si tu passes --authorized (l'auteur t'a donné son accord).
"""
import re
import shutil
import subprocess
from pathlib import Path

from .config import SOURCES_DIR

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


class RightsError(RuntimeError):
    pass


def _videos_in(folder: Path):
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in VIDEO_EXT)


def fetch(source: str, authorized: bool = False) -> list[Path]:
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    p = Path(source).expanduser()
    if p.exists():
        return _videos_in(p) if p.is_dir() else [p.resolve()]

    if "drive.google.com" in source or "drive.usercontent.google.com" in source:
        return _fetch_drive(source)

    if re.match(r"https?://", source):
        return [_fetch_ytdlp(source, authorized)]

    raise FileNotFoundError(f"Source introuvable : {source}")


def _fetch_drive(url: str) -> list[Path]:
    import gdown

    dest = SOURCES_DIR / "drive"
    dest.mkdir(parents=True, exist_ok=True)
    if "/folders/" in url:
        gdown.download_folder(url=url, output=str(dest), quiet=False, use_cookies=False)
        return _videos_in(dest)
    out = gdown.download(url=url, output=str(dest) + "/", quiet=False, fuzzy=True)
    if not out:
        raise RuntimeError("Téléchargement Drive impossible : le fichier est-il partagé par lien ?")
    return [Path(out).resolve()]


def _fetch_ytdlp(url: str, authorized: bool) -> Path:
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    lic = (info.get("license") or "").lower()
    if "creative commons" not in lic and not authorized:
        raise RightsError(
            f"« {info.get('title')} » n'est pas sous licence Creative Commons (licence : "
            f"{info.get('license') or 'standard'}). Refusé. Si l'auteur t'a donné son accord, "
            "relance avec --authorized."
        )
    opts = {
        "outtmpl": str(SOURCES_DIR / "%(id)s.%(ext)s"),
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
    credit = SOURCES_DIR / f"{path.stem}.credit.txt"
    credit.write_text(
        f"Titre : {info.get('title')}\nAuteur : {info.get('uploader')}\nURL : {url}\n"
        f"Licence : {info.get('license') or 'accord de l’auteur'}\n", encoding="utf-8")
    return path


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)
    ], text=True)
    return float(out.strip())


def has_audio(path: Path) -> bool:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
        "-of", "csv=p=0", str(path)], text=True)
    return bool(out.strip())


def require(binary: str):
    if not shutil.which(binary):
        raise RuntimeError(f"{binary} est requis.")
