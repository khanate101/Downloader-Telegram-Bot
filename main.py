import asyncio
import secrets
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from config import load_settings
from database import Database
from keyboards import platforms, media, youtube, admin, user_admin
import media as downloader
import instagram
import tiktok

S = load_settings()
bot = Bot(S.telegram_bot_token)
dp = Dispatcher()
db = Database()
CACHE = {}
ADMIN_MODE = {}


async def guard(m):
    u = await db.user(m.from_user)
    if u.is_banned:
        await m.answer("🚫 تم حظر حسابك من استخدام البوت.")
        return None
    return u


@dp.message(CommandStart())
async def start(m):
    if await guard(m):
        await m.answer(
            "👋 أهلاً بك.\n"
            "🔗 أرسل رابطًا للتحميل.\n"
            "👤 أرسل @username للبحث عن حساب Instagram أو TikTok.\n"
            "▶️ أرسل «بحث يوتيوب» أو استخدم /youtube للبحث في YouTube."
        )


@dp.message(Command("admin"))
async def admin_cmd(m):
    if m.from_user.id != S.admin_id:
        return await m.answer("⛔ غير مصرح.")
    await m.answer("👑 لوحة التحكم", reply_markup=admin())


@dp.message(Command("youtube"))
async def yt_cmd(m, state: FSMContext):
    if not await guard(m):
        return
    await m.answer("🔎 أرسل عبارة البحث في YouTube:")
    await state.set_state("yt")


@dp.message()
async def text(m, state: FSMContext):
    u = await guard(m)
    if not u:
        return

    q = (m.text or "").strip()
    st = await state.get_state()

    # Keep the existing YouTube search flow.
    if st == "yt":
        await state.clear()
        await send_youtube(m, q)
        return

    if m.from_user.id == S.admin_id and m.from_user.id in ADMIN_MODE:
        await admin_text(m)
        return

    if q.startswith("بحث يوتيوب"):
        await m.answer("🔎 أرسل عبارة البحث في YouTube:")
        await state.set_state("yt")
        return

    # Any URL is treated as a direct media/story download.
    if q.startswith("http://") or q.startswith("https://"):
        await send_url(m, q)
        return

    # Username search only. Hashtag search has intentionally been removed.
    if q.startswith("@") and len(q) > 1:
        await m.answer("🔎 اختر المنصة:", reply_markup=platforms("user", q[1:]))
        return

    await m.answer(
        "أرسل رابطًا للتحميل، أو @username للبحث عن حساب Instagram/TikTok، "
        "أو استخدم «بحث يوتيوب» للبحث في YouTube."
    )


async def send_url(m, url):
    wait = await m.answer("⏳ جارٍ التحميل...")
    token = secrets.token_urlsafe(8)
    CACHE[token] = {"url": url, "platform": "direct"}
    path = None

    try:
        path, info = await downloader.download(url, S.download_dir)
        ext = Path(path).suffix.lower()
        cap = "✅ تم التحميل"

        if ext in {".jpg", ".jpeg", ".png", ".webp"}:
            await bot.send_photo(
                m.chat.id,
                FSInputFile(path),
                caption=cap,
                reply_markup=media(token, url),
            )
        else:
            await bot.send_video(
                m.chat.id,
                FSInputFile(path),
                caption=cap,
                reply_markup=media(token, url),
            )

        u = await db.get(m.from_user.id)
        if u:
            await db.inc(m.from_user.id, "downloads")
            await db.event(
                u.id,
                "download",
                info.get("extractor_key", "unknown"),
                url,
            )

        await wait.delete()

    except Exception:
        await wait.edit_text(
            "❌ تعذر التحميل. تأكد أن الرابط عام ومدعوم، "
            "وأن الملف ليس أكبر من الحد المسموح به في Telegram."
        )
    finally:
        if path:
            Path(path).unlink(missing_ok=True)


@dp.callback_query(F.data.startswith("user:"))
async def search_user(c):
    await c.answer()
    _, platform_name, username = c.data.split(":", 2)

    status = await c.message.edit_text("⏳ جارٍ البحث عن بيانات الحساب...")

    try:
        # A timeout prevents Instagram/TikTok from leaving the bot stuck forever.
        if platform_name == "instagram":
            data = await asyncio.wait_for(instagram.profile(username), timeout=30)
        elif platform_name == "tiktok":
            data = await asyncio.wait_for(tiktok.profile(username), timeout=30)
        else:
            raise RuntimeError("unsupported platform")

        text = (
            f"👤 <b>{data.get('name') or username}</b>\n"
            f"🔗 @{data.get('username') or username}\n"
            f"📝 {data.get('bio') or 'لا توجد نبذة'}\n"
            f"👥 المتابعون: {data.get('followers', '-')}\n"
            f"❤️ الإعجابات: {data.get('likes', '-')}\n"
            f"🎬 المحتوى: {data.get('videos', data.get('posts', '-'))}\n"
            f"{'🔒 الحساب خاص' if data.get('private') else '🔓 الحساب عام'}"
        )

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📸 القصص العامة",
                        callback_data=f"story:{platform_name}:{username}",
                    )
                ]
            ]
        )

        await status.delete()

        if data.get("picture"):
            await c.message.answer_photo(
                data["picture"],
                caption=text,
                parse_mode="HTML",
                reply_markup=kb,
            )
        else:
            await c.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=kb,
            )

        u = await db.get(c.from_user.id)
        if u:
            await db.event(u.id, "profile_search", platform_name, username)

    except asyncio.TimeoutError:
        await status.edit_text(
            f"❌ انتهت مهلة البحث في {platform_name}. "
            "قد تكون المنصة تمنع الوصول حاليًا. حاول مرة أخرى."
        )
    except Exception:
        await status.edit_text(
            f"❌ تعذر جلب بيانات حساب {platform_name} حاليًا. "
            "إذا كان الحساب خاصًا فلن يتم تجاوز الخصوصية."
        )


@dp.callback_query(F.data.startswith("story:"))
async def story(c):
    await c.answer()
    _, platform_name, username = c.data.split(":", 2)

    # Public story access varies by platform. Direct story URLs are always
    # accepted by the normal URL downloader when yt-dlp supports that URL.
    if platform_name == "instagram":
        items = await asyncio.wait_for(instagram.stories(username), timeout=30)
    elif platform_name == "tiktok":
        items = await asyncio.wait_for(tiktok.stories(username), timeout=30)
    else:
        items = []

    if not items:
        return await c.message.answer(
            "📸 لا توجد Stories عامة متاحة حاليًا من هذا الحساب بالطريقة العامة.\n"
            "إذا كان لديك رابط Story مباشر، أرسله للبوت وسيحاول تحميله بالطريقة العادية."
        )

    for item in items:
        token = secrets.token_urlsafe(9)
        CACHE[token] = {"url": item.url, "platform": platform_name}
        caption = f"📸 {platform_name}\n{item.title}\n{item.meta}"
        try:
            if item.thumb:
                await c.message.answer_photo(
                    item.thumb,
                    caption=caption,
                    reply_markup=media(token, item.url),
                )
            else:
                await c.message.answer(caption, reply_markup=media(token, item.url))
        except Exception:
            await c.message.answer(caption, reply_markup=media(token, item.url))


@dp.callback_query(F.data.startswith("result:"))
async def result_cb(c):
    await c.answer("⏳ جاري التحميل...")
    x = CACHE.get(c.data.split(":", 1)[1])
    if not x:
        return await c.message.answer("انتهت صلاحية النتيجة.")
    await send_url(c.message, x["url"])


@dp.callback_query(F.data.startswith("audio:"))
async def audio_cb(c):
    await c.answer("⏳")
    x = CACHE.get(c.data.split(":", 1)[1])
    if not x:
        return await c.message.answer("انتهت صلاحية العملية.")

    path = None
    audio_path = None
    try:
        path, _ = await downloader.download(x["url"], S.download_dir)
        audio_path = await downloader.audio(path)
        await bot.send_audio(
            c.from_user.id,
            FSInputFile(audio_path),
            caption="🎵 تم التحويل إلى صوت",
        )
        await db.inc(c.from_user.id, "audio_conversions")
    except Exception:
        await c.message.answer("❌ تعذر تحويل الفيديو إلى صوت.")
    finally:
        if path:
            Path(path).unlink(missing_ok=True)
        if audio_path:
            Path(audio_path).unlink(missing_ok=True)


@dp.callback_query(F.data.startswith("ytaudio:"))
async def ytaudio(c):
    await c.answer("⏳")
    x = CACHE.get(c.data.split(":", 1)[1])
    if not x:
        return await c.message.answer("انتهت صلاحية العملية.")

    path = None
    audio_path = None
    try:
        path, _ = await downloader.download(x["url"], S.download_dir)
        audio_path = await downloader.audio(path)
        await bot.send_audio(
            c.from_user.id,
            FSInputFile(audio_path),
            caption="🎵 تم تحميل الصوت",
        )
        await db.inc(c.from_user.id, "audio_conversions")
    except Exception:
        await c.message.answer("❌ تعذر تحميل الصوت.")
    finally:
        if path:
            Path(path).unlink(missing_ok=True)
        if audio_path:
            Path(audio_path).unlink(missing_ok=True)


async def send_youtube(m, q):
    await m.answer("⏳ جارٍ البحث في YouTube...")
    try:
        items = await downloader.youtube_search(q)
        await results_youtube(m, items)
    except Exception:
        await m.answer("❌ تعذر البحث في YouTube حاليًا.")


async def results_youtube(m, items):
    if not items:
        return await m.answer("لم يتم العثور على نتائج.")

    for x in items[:10]:
        token = secrets.token_urlsafe(9)
        CACHE[token] = {"url": x.url, "platform": "youtube"}
        cap = (
            f"▶️ YouTube\n"
            f"🎬 {x.title}\n"
            f"{x.meta}"
        )

        if x.thumb:
            try:
                await m.answer_photo(
                    x.thumb,
                    caption=cap,
                    reply_markup=youtube(token),
                )
            except Exception:
                await m.answer(cap, reply_markup=youtube(token))
        else:
            await m.answer(cap, reply_markup=youtube(token))


@dp.callback_query(F.data.startswith("admin:"))
async def admin_cb(c):
    if c.from_user.id != S.admin_id:
        return await c.answer("غير مصرح", show_alert=True)

    await c.answer()
    action = c.data.split(":", 1)[1]

    if action == "users":
        rows = await db.users()
        p = Path("users.txt")
        p.write_text(
            "\n".join(
                f"{u.telegram_id} | {u.first_name or ''} | @{u.username or '-'}"
                for u in rows
            ),
            encoding="utf-8",
        )
        await c.message.answer_document(FSInputFile(p))
        p.unlink(missing_ok=True)

    elif action == "stats":
        n, d, aud, plat = await db.stats()
        top = (
            "\n".join(f"• {p or 'unknown'}: {v}" for p, v in plat)
            or "لا توجد بيانات"
        )
        await c.message.answer(
            f"📊 الإحصائيات\n\n"
            f"👥 المستخدمون: {n}\n"
            f"📥 التحميلات: {d}\n"
            f"🎵 التحويلات: {aud}\n\n"
            f"🔥 المنصات:\n{top}"
        )

    elif action == "broadcast":
        ADMIN_MODE[c.from_user.id] = "broadcast"
        await c.message.answer("📢 أرسل الرسالة:")

    elif action == "user":
        ADMIN_MODE[c.from_user.id] = "user"
        await c.message.answer("🔎 أرسل Telegram ID:")


@dp.callback_query(F.data.startswith(("ban:", "unban:", "notify:")))
async def user_action(c):
    if c.from_user.id != S.admin_id:
        return await c.answer("غير مصرح", show_alert=True)

    action, tid_text = c.data.split(":")
    tid = int(tid_text)
    u = await db.get(tid)

    if not u:
        return await c.answer("المستخدم غير موجود", show_alert=True)

    if action == "notify":
        ADMIN_MODE[c.from_user.id] = f"notify:{tid}"
        await c.message.answer("📩 أرسل الرسالة:")
    else:
        async with db.sessions() as s:
            from sqlalchemy import select
            from database import User

            obj = (
                await s.execute(select(User).where(User.telegram_id == tid))
            ).scalar_one()

            obj.is_banned = action == "ban"
            await s.commit()

        await c.message.answer(
            "✅ تم تحديث الحالة.",
            reply_markup=user_admin(tid),
        )

    await c.answer()


async def admin_text(m):
    mode = ADMIN_MODE.pop(m.from_user.id, None)

    if mode == "broadcast":
        n = 0
        for u in await db.users():
            if u.is_banned:
                continue
            try:
                await bot.copy_message(u.telegram_id, m.chat.id, m.message_id)
                n += 1
            except Exception:
                pass
        await m.answer(f"✅ تم الإرسال إلى {n} مستخدم.")

    elif mode == "user" and (m.text or "").isdigit():
        u = await db.get(int(m.text))
        if not u:
            return await m.answer("المستخدم غير موجود.")

        await m.answer(
            f"👤 {u.first_name or ''}\n"
            f"@{u.username or '-'}\n"
            f"ID: {u.telegram_id}\n"
            f"📅 انضم: {u.joined_at}\n"
            f"🕐 آخر نشاط: {u.last_activity}\n"
            f"📥 التحميلات: {u.downloads}\n"
            f"🎵 التحويلات: {u.audio_conversions}\n"
            f"{'🚫 محظور' if u.is_banned else '🟢 نشط'}",
            reply_markup=user_admin(u.telegram_id),
        )

    elif mode and mode.startswith("notify:"):
        tid = int(mode.split(":")[1])
        try:
            await bot.copy_message(tid, m.chat.id, m.message_id)
            await m.answer("✅ تم الإرسال.")
        except Exception:
            await m.answer("❌ تعذر الإرسال.")


async def main():
    await db.init()
    Path(S.download_dir).mkdir(exist_ok=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
