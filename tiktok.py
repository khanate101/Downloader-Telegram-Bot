import asyncio, json, re, httpx

async def _html(url):
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.text


def _data(h):
    for sid in ("__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE"):
        m = re.search(r'<script[^>]+id="' + sid + r'"[^>]*>(.*?)</script>', h, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
    return {}


def _user(x):
    if isinstance(x, dict):
        ui = x.get("userInfo")
        if isinstance(ui, dict) and ui.get("user"):
            return ui["user"]
        for v in x.values():
            z = _user(v)
            if z:
                return z
    if isinstance(x, list):
        for v in x:
            z = _user(v)
            if z:
                return z
    return {}


async def profile(name):
    d = _data(await _html(f"https://www.tiktok.com/@{name}"))
    u = _user(d)
    if not u:
        raise RuntimeError("public profile not found")
    s = u.get("stats") or {}
    return {
        "username": u.get("uniqueId", name),
        "name": u.get("nickname") or name,
        "bio": u.get("signature") or "",
        "followers": s.get("followerCount"),
        "likes": s.get("heartCount"),
        "videos": s.get("videoCount"),
        "private": bool(u.get("privateAccount")),
        "picture": u.get("avatarLarger"),
    }


async def stories(name):
    return []
