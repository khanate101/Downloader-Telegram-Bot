import asyncio, instaloader
from dataclasses import dataclass

@dataclass
class Result:
    title:str
    url:str
    thumb:str|None=None
    meta:str=""

async def profile(name):
    def run():
        L=instaloader.Instaloader(quiet=True)
        p=instaloader.Profile.from_username(L.context,name)
        return {"username":p.username,"name":p.full_name or p.username,"bio":p.biography or "",
                "followers":p.followers,"following":p.followees,"posts":p.mediacount,
                "private":p.is_private,"picture":p.profile_pic_url}
    return await asyncio.to_thread(run)

async def hashtag(tag,limit=10):
    def run():
        L=instaloader.Instaloader(quiet=True); h=instaloader.Hashtag.from_name(L.context,tag.lstrip("#")); out=[]
        for p in h.get_posts():
            out.append(Result((p.caption or "بدون وصف")[:200],f"https://www.instagram.com/p/{p.shortcode}/",p.url,
                              f"@{p.owner_username} • ❤️ {p.likes} • 💬 {p.comments}"))
            if len(out)>=limit: break
        return out
    return await asyncio.to_thread(run)

async def stories(name):
    # Stories commonly require authenticated access. No user passwords/cookies are collected.
    return []
