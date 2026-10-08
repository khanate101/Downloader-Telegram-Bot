import asyncio,json,re,httpx
from dataclasses import dataclass

@dataclass
class Result:
    title:str
    url:str
    thumb:str|None=None
    meta:str=""

async def _html(url):
    async with httpx.AsyncClient(follow_redirects=True,timeout=20,headers={"User-Agent":"Mozilla/5.0"}) as c:
        r=await c.get(url); r.raise_for_status(); return r.text

def _data(h):
    for sid in ("__UNIVERSAL_DATA_FOR_REHYDRATION__","SIGI_STATE"):
        m=re.search(r'<script[^>]+id="'+sid+r'"[^>]*>(.*?)</script>',h,re.S)
        if m:
            try:return json.loads(m.group(1))
            except:pass
    return {}

def _user(x):
    if isinstance(x,dict):
        ui=x.get("userInfo")
        if isinstance(ui,dict) and ui.get("user"): return ui["user"]
        for v in x.values():
            z=_user(v)
            if z:return z
    if isinstance(x,list):
        for v in x:
            z=_user(v)
            if z:return z
    return {}

async def profile(name):
    d=_data(await _html(f"https://www.tiktok.com/@{name}")); u=_user(d)
    if not u: raise RuntimeError("public profile not found")
    s=u.get("stats") or {}
    return {"username":u.get("uniqueId",name),"name":u.get("nickname") or name,"bio":u.get("signature") or "",
            "followers":s.get("followerCount"),"likes":s.get("heartCount"),"videos":s.get("videoCount"),
            "private":bool(u.get("privateAccount")),"picture":u.get("avatarLarger")}

async def hashtag(tag,limit=10):
    # Best-effort public web connector. TikTok can change this schema at any time.
    d=_data(await _html(f"https://www.tiktok.com/tag/{tag.lstrip('#')}")); out=[]
    def walk(x):
        if len(out)>=limit:return
        if isinstance(x,dict):
            it=x.get("itemStruct")
            if isinstance(it,dict) and it.get("id"):
                a=it.get("author") or {}; uid=a.get("uniqueId",""); st=it.get("stats") or {}
                out.append(Result((it.get("desc") or "TikTok")[:200],f"https://www.tiktok.com/@{uid}/video/{it['id']}",(it.get("video") or {}).get("cover"),
                                  f"@{uid} • ▶️ {st.get('playCount','-')} • ❤️ {st.get('diggCount','-')}"))
            for v in x.values(): walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(d); return out[:limit]

async def stories(name):
    return []
