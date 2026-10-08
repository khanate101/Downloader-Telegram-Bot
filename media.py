import asyncio, subprocess
from dataclasses import dataclass
from pathlib import Path
import yt_dlp

@dataclass
class Result:
    title:str
    url:str
    thumb:str|None=None
    meta:str=""

async def download(url,folder="downloads"):
    Path(folder).mkdir(exist_ok=True)
    opts={"quiet":True,"no_warnings":True,"noplaylist":True,"outtmpl":str(Path(folder)/"%(id)s.%(ext)s"),
          "format":"bv*+ba/b","merge_output_format":"mp4","restrictfilenames":True}
    def run():
        with yt_dlp.YoutubeDL(opts) as y:
            info=y.extract_info(url,download=True)
            path=info.get("_filename")
            if not path: path=str(Path(folder)/(info.get("id","media")+"."+info.get("ext","mp4")))
            return path,info
    return await asyncio.to_thread(run)

async def youtube_search(q,limit=10):
    def run():
        with yt_dlp.YoutubeDL({"quiet":True,"no_warnings":True,"extract_flat":True}) as y:
            data=y.extract_info(f"ytsearch{limit}:{q}",download=False)
            out=[]
            for x in data.get("entries",[])[:limit]:
                if not x: continue
                vid=x.get("id"); url=x.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
                out.append(Result((x.get("title") or "YouTube")[:200],url,x.get("thumbnail"),
                                  f"👤 {x.get('channel') or x.get('uploader') or '-'} • ⏱️ {x.get('duration_string') or x.get('duration') or '-'} • 👁️ {x.get('view_count') or '-'}"))
            return out
    return await asyncio.to_thread(run)

async def audio(path):
    src=Path(path); dst=src.with_suffix(".mp3")
    await asyncio.to_thread(subprocess.run,["ffmpeg","-y","-i",str(src),"-vn","-codec:a","libmp3lame","-q:a","2",str(dst)],
                            check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return str(dst)
