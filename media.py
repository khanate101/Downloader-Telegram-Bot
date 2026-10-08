import asyncio, subprocess
from dataclasses import dataclass
from pathlib import Path
import yt_dlp

@dataclass
class Result:
    title: str
    url: str
    thumb: str | None = None
    meta: str = ""

async def download(url, folder="downloads"):
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": str(folder_path / "%(id)s.%(ext)s"),
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "restrictfilenames": True,
    }

    def run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            media_id = info.get("id") or "media"
            candidates = []
            for item in info.get("requested_downloads") or []:
                filepath = item.get("filepath")
                if filepath:
                    candidates.append(Path(filepath))
            prepared = Path(ydl.prepare_filename(info))
            candidates.extend([prepared, prepared.with_suffix(".mp4"),
                               folder_path / f"{media_id}.mp4"])
            candidates.extend(folder_path.glob(f"{media_id}.*"))
            for candidate in candidates:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    return str(candidate), info
            raise FileNotFoundError(f"Final media file not found for {media_id}")

    return await asyncio.to_thread(run)

async def youtube_search(q, limit=10):
    def run():
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True}) as ydl:
            data = ydl.extract_info(f"ytsearch{limit}:{q}", download=False)
            out = []
            for x in data.get("entries", [])[:limit]:
                if not x:
                    continue
                vid = x.get("id")
                url = x.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
                out.append(Result((x.get("title") or "YouTube")[:200], url,
                    x.get("thumbnail"),
                    f"👤 {x.get('channel') or x.get('uploader') or '-'} • "
                    f"⏱️ {x.get('duration_string') or x.get('duration') or '-'} • "
                    f"👁️ {x.get('view_count') or '-'}"))
            return out
    return await asyncio.to_thread(run)

async def audio(path):
    src = Path(path)
    dst = src.with_suffix(".mp3")
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-i", str(src), "-vn", "-codec:a", "libmp3lame", "-q:a", "2", str(dst)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(dst)
