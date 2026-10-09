import asyncio
import hashlib
import json
import os
import re
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

def _find_video_url(obj):
    if isinstance(obj, dict):
        for key in ("playAddr", "downloadAddr", "playApi", "download_url", "play_url"):
            value = obj.get(key)
            if isinstance(value, str) and "http" in value:
                return value.replace("\\u002F", "/").replace("\\u0026", "&").replace("\\/", "/")
        for value in obj.values():
            found = _find_video_url(value)
            if found: return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_video_url(value)
            if found: return found
    return None

async def _download_tiktok_direct(url: str, folder_path: Path):
    host = (urlparse(url).hostname or "").lower()
    if not (host.endswith("tiktok.com") or host.endswith("tiktokv.com")):
        return None
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=25, headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36",
            "Referer": "https://www.tiktok.com/",
            "Accept-Language": "en-US,en;q=0.9",
        }) as client:
            page = await client.get(url)
            page.raise_for_status()
            for script_id in ("__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE"):
                match = re.search(r'<script[^>]+id=["\\\']' + re.escape(script_id) + r'["\\\'][^>]*>(.*?)</script>', page.text, re.S)
                if not match: continue
                try: data = json.loads(match.group(1))
                except Exception: continue
                video_url = _find_video_url(data)
                if not video_url: continue
                r = await client.get(video_url, follow_redirects=True)
                r.raise_for_status()
                if len(r.content) < 10000: continue
                target = folder_path / ("tiktok_" + hashlib.sha1(video_url.encode()).hexdigest()[:16] + ".mp4")
                target.write_bytes(r.content)
                return str(_compress_video(target)), {"extractor_key": "TikTok"}
    except Exception:
        return None
    return None

async def download(url, folder="downloads"):
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    resolved = await _resolve_special_url(url)
    direct_tiktok = await _download_tiktok_direct(resolved, folder_path)
    if direct_tiktok:
        return direct_tiktok
    host = (urlparse(resolved).hostname or "").lower()
    is_youtube = host.endswith("youtube.com") or host.endswith("youtu.be") or host.endswith("youtube-nocookie.com")

    def run():
        attempts = []
        if is_youtube:
            # GitHub-hosted runners are often rate-limited by YouTube. Try
            # several supported clients, and optionally use a user-supplied
            # cookies file (never commit cookies into the repository).
            cookie_file = os.getenv("YOUTUBE_COOKIES_FILE", "").strip()
            base_formats = [
                "best[ext=mp4][height<=480]/best[height<=480]",
                "best[ext=mp4][height<=360]/best[height<=360]",
            ]
            for client in ("android_vr", "ios", "mweb", "web"):
                for fmt in base_formats:
                    attempt = {
                        "format": fmt,
                        "extractor_args": {"youtube": {"player_client": [client]}},
                    }
                    if cookie_file and Path(cookie_file).is_file():
                        attempt["cookiefile"] = cookie_file
                    attempts.append(attempt)
            # Last fallback lets yt-dlp choose its default client strategy.
            fallback = {"format": "best[ext=mp4][height<=360]/best[height<=360]"}
            if cookie_file and Path(cookie_file).is_file():
                fallback["cookiefile"] = cookie_file
            attempts.append(fallback)
        else:
            attempts.append({"format": "best[ext=mp4][height<=720]/best[height<=720]/best"})

        last_error = None
        for attempt in attempts:
            opts = {
                "quiet": True, "no_warnings": True, "noplaylist": True,
                "outtmpl": str(folder_path / "%(id)s.%(ext)s"),
                "merge_output_format": "mp4", "restrictfilenames": True,
                "retries": 2, "fragment_retries": 2, **attempt,
            }
            try:
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
                            if candidate.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
                                candidate = _compress_video(candidate)
                            return str(candidate), info
            except Exception as exc:
                last_error = exc
        error_text = str(last_error or "unknown error")
        if is_youtube and ("Sign in to confirm" in error_text or "not a bot" in error_text.lower()):
            raise RuntimeError(
                "YouTube blocked this server IP and requested authentication. "
                "Set YOUTUBE_COOKIES_FILE to a valid exported YouTube cookies file, "
                "or retry later from a different trusted host."
            ) from last_error
        raise RuntimeError(f"yt-dlp download failed: {error_text}")

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
