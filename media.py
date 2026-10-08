import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yt_dlp

MAX_TELEGRAM_BYTES = 48 * 1024 * 1024

@dataclass
class Result:
    title: str
    url: str
    thumb: str | None = None
    meta: str = ""

async def _resolve_special_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if not (host.endswith("tiktok.com") or host.endswith("tiktokv.com")):
        return url
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get(url)
            return str(r.url)
    except Exception:
        return url

def _compress_video(path: Path) -> Path:
    if path.stat().st_size <= MAX_TELEGRAM_BYTES:
        return path
    out = path.with_name(path.stem + "_telegram.mp4")
    for crf in (28, 31, 34, 37):
        tmp = out.with_name(out.stem + f"_{crf}.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-i", str(path), "-vf", "scale='min(720,iw)':-2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(tmp)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if tmp.stat().st_size <= MAX_TELEGRAM_BYTES:
            tmp.replace(out)
            path.unlink(missing_ok=True)
            return out
        tmp.unlink(missing_ok=True)
    raise ValueError("Downloaded video is too large for Telegram")

async def download(url, folder="downloads"):
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    resolved = await _resolve_special_url(url)
    opts = {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "outtmpl": str(folder_path / "%(id)s.%(ext)s"),
        "format": "best[ext=mp4][height<=720]/best[height<=720]/best",
        "merge_output_format": "mp4", "restrictfilenames": True,
    }
    def run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(resolved, download=True)
            media_id = info.get("id") or "media"
            candidates = []
            for item in info.get("requested_downloads") or []:
                if item.get("filepath"):
                    candidates.append(Path(item["filepath"]))
            prepared = Path(ydl.prepare_filename(info))
            candidates.extend([prepared, prepared.with_suffix(".mp4"), folder_path / f"{media_id}.mp4"])
            candidates.extend(folder_path.glob(f"{media_id}.*"))
            for candidate in candidates:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    final = _compress_video(candidate) if candidate.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"} else candidate
                    return str(final), info
            raise FileNotFoundError(f"Final media file not found for {media_id}")
    return await asyncio.to_thread(run)

async def youtube_search(q, limit=10):
    def run():
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True}) as ydl:
            data = ydl.extract_info(f"ytsearch{limit}:{q}", download=False)
            out = []
            for x in data.get("entries", [])[:limit]:
                if not x: continue
                vid = x.get("id")
                url = x.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
                out.append(Result((x.get("title") or "YouTube")[:200], url, x.get("thumbnail"),
                    f"👤 {x.get('channel') or x.get('uploader') or '-'} • "
                    f"⏱️ {x.get('duration_string') or x.get('duration') or '-'} • "
                    f"👁️ {x.get('view_count') or '-'}"))
            return out
    return await asyncio.to_thread(run)

async def audio(path):
    src = Path(path)
    dst = src.with_suffix(".mp3")
    await asyncio.to_thread(subprocess.run, ["ffmpeg", "-y", "-i", str(src), "-vn", "-codec:a", "libmp3lame", "-b:a", "128k", str(dst)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if dst.stat().st_size > MAX_TELEGRAM_BYTES:
        smaller = dst.with_name(dst.stem + "_telegram.mp3")
        await asyncio.to_thread(subprocess.run, ["ffmpeg", "-y", "-i", str(dst), "-b:a", "64k", str(smaller)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dst.unlink(missing_ok=True)
        smaller.replace(dst)
    return str(dst)
