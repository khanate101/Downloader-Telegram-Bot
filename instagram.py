import asyncio, instaloader

async def profile(name):
    def run():
        L = instaloader.Instaloader(quiet=True)
        p = instaloader.Profile.from_username(L.context, name)
        return {
            "username": p.username,
            "name": p.full_name or p.username,
            "bio": p.biography or "",
            "followers": p.followers,
            "following": p.followees,
            "posts": p.mediacount,
            "private": p.is_private,
            "picture": p.profile_pic_url,
        }
    return await asyncio.to_thread(run)

async def stories(name):
    # Public story access commonly requires an authenticated session.
    return []
