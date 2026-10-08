import asyncio,secrets
from pathlib import Path
from aiogram import Bot,Dispatcher,F
from aiogram.filters import CommandStart,Command
from aiogram.types import Message,CallbackQuery,FSInputFile
from aiogram.fsm.context import FSMContext
from config import load_settings
from database import Database
from keyboards import platforms,media,result,youtube,admin,user_admin
import media as downloader, instagram, tiktok

S=load_settings(); bot=Bot(S.telegram_bot_token); dp=Dispatcher(); db=Database(); CACHE={}; ADMIN_MODE={}

async def guard(m):
    u=await db.user(m.from_user)
    if u.is_banned: await m.answer("🚫 تم حظر حسابك من استخدام البوت."); return None
    return u

@dp.message(CommandStart())
async def start(m): 
    if await guard(m): await m.answer("👋 أهلاً بك.\n🔗 أرسل رابطًا للتحميل.\n👤 أرسل @username للبحث.\n#️⃣ أرسل #هاشتاج للبحث.\n▶️ أرسل «بحث يوتيوب» أو /youtube.")

@dp.message(Command("admin"))
async def admin_cmd(m):
    if m.from_user.id!=S.admin_id:return await m.answer("⛔ غير مصرح.")
    await m.answer("👑 لوحة التحكم",reply_markup=admin())

@dp.message(Command("youtube"))
async def yt_cmd(m,state:FSMContext):
    await guard(m); await m.answer("🔎 أرسل عبارة البحث في YouTube:"); await state.set_state("yt")

@dp.message()
async def text(m,state:FSMContext):
    u=await guard(m)
    if not u:return
    q=(m.text or "").strip(); st=await state.get_state()
    if st=="yt":
        await state.clear(); await send_youtube(m,q); return
    if m.from_user.id==S.admin_id and m.from_user.id in ADMIN_MODE:
        await admin_text(m); return
    if q.startswith("بحث يوتيوب"):
        await m.answer("🔎 أرسل عبارة البحث في YouTube:"); await state.set_state("yt"); return
    if q.startswith("http://") or q.startswith("https://"): await send_url(m,q); return
    if q.startswith("@") and len(q)>1:
        await m.answer("🔎 اختر المنصة:",reply_markup=platforms("user",q[1:])); return
    if q.startswith("#") and len(q)>1:
        await m.answer(f"🔎 اختر المنصة للبحث عن {q}",reply_markup=platforms("tag",q[1:])); return
    await m.answer("أرسل رابطًا أو @username أو #هاشتاج.")

async def send_url(m,url):
    wait=await m.answer("⏳ جارٍ التحميل...")
    try:
        token=secrets.token_urlsafe(8); CACHE[token]={"url":url,"platform":"direct"}
        path,info=await downloader.download(url,S.download_dir)
        ext=Path(path).suffix.lower(); cap="✅ تم التحميل"
        if ext in {".jpg",".jpeg",".png",".webp"}: await bot.send_photo(m.chat.id,FSInputFile(path),caption=cap,reply_markup=media((token:=secrets.token_urlsafe(8)),url))
        else: await bot.send_video(m.chat.id,FSInputFile(path),caption=cap,reply_markup=media(secrets.token_urlsafe(8)))
        u=await db.get(m.from_user.id); await db.inc(m.from_user.id,"downloads"); await db.event(u.id,"download",info.get("extractor_key","unknown"),url)
        Path(path).unlink(missing_ok=True); await wait.delete()
    except Exception: await wait.edit_text("❌ تعذر التحميل. تأكد أن الرابط عام ومدعوم.")

@dp.callback_query(F.data.startswith(("user:","tag:")))
async def search(c):
    await c.answer(); kind,p,q=c.data.split(":",2); await c.message.edit_text("⏳ جارٍ البحث...")
    try:
        if kind=="user":
            if p=="instagram": d=await instagram.profile(q)
            elif p=="tiktok": d=await tiktok.profile(q)
            else: raise RuntimeError()
            text=(f"👤 <b>{d['name']}</b>\n🔗 @{d['username']}\n📝 {d['bio']}\n👥 المتابعون: {d.get('followers','-')}\n❤️ الإعجابات: {d.get('likes','-')}\n🎬 المحتوى: {d.get('videos',d.get('posts','-'))}\n{'🔒 الحساب خاص' if d['private'] else '🔓 الحساب عام'}")
            from aiogram.types import InlineKeyboardMarkup,InlineKeyboardButton
            kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📸 القصص العامة",callback_data=f"story:{p}:{q}")]])
            if d.get("picture"): await c.message.answer_photo(d["picture"],caption=text,parse_mode="HTML",reply_markup=kb)
            else: await c.message.answer(text,parse_mode="HTML",reply_markup=kb)
            u=await db.get(c.from_user.id); await db.event(u.id,"profile_search",p,q)
        else:
            items=await (instagram.hashtag(q) if p=="instagram" else tiktok.hashtag(q) if p=="tiktok" else downloader.youtube_search("#"+q))
            await results(c.message,items,p)
    except Exception: await c.message.answer("❌ تعذر جلب البيانات العامة من المنصة حاليًا.")

async def results(m,items,p):
    if not items:return await m.answer("لم يتم العثور على نتائج عامة.")
    for x in items[:10]:
        token=secrets.token_urlsafe(9); CACHE[token]={"url":x.url,"platform":p}
        cap=f"📱 {p}\n📝 {x.title}\n{x.meta}"
        try:
            if x.thumb: await m.answer_photo(x.thumb,caption=cap,reply_markup=result(token))
            else: await m.answer(cap,reply_markup=result(token))
        except Exception: await m.answer(cap,reply_markup=result(token))

@dp.callback_query(F.data.startswith("story:"))
async def story(c):
    await c.answer()
    _,p,q=c.data.split(":",2)
    items=await (instagram.stories(q) if p=="instagram" else tiktok.stories(q))
    if not items: return await c.message.answer("🔒 لا توجد Stories عامة يمكن الوصول إليها بالطريقة العامة الحالية. لا يتم تجاوز الحسابات الخاصة أو طلب كلمات مرور.")
    await results(c.message,items,p)

@dp.callback_query(F.data.startswith("result:"))
async def result_cb(c):
    await c.answer("⏳ جاري التحميل...")
    x=CACHE.get(c.data.split(":",1)[1])
    if not x:return await c.message.answer("انتهت صلاحية النتيجة.")
    await send_url(c.message,x["url"])

@dp.callback_query(F.data.startswith("audio:"))
async def audio_cb(c):
    await c.answer("⏳")
    x=CACHE.get(c.data.split(":",1)[1])
    if not x:return await c.message.answer("انتهت صلاحية العملية.")
    try:
        path,_=await downloader.download(x["url"],S.download_dir); a=await downloader.audio(path)
        await bot.send_audio(c.from_user.id,FSInputFile(a),caption="🎵 تم التحويل إلى صوت")
        await db.inc(c.from_user.id,"audio_conversions"); Path(path).unlink(missing_ok=True); Path(a).unlink(missing_ok=True)
    except Exception: await c.message.answer("❌ تعذر تحويل الفيديو إلى صوت.")

@dp.callback_query(F.data.startswith("ytaudio:"))
async def ytaudio(c):
    await c.answer("⏳")
    x=CACHE.get(c.data.split(":",1)[1])
    if not x:return
    try:
        path,_=await downloader.download(x["url"],S.download_dir); a=await downloader.audio(path)
        await bot.send_audio(c.from_user.id,FSInputFile(a),caption="🎵 تم تحميل الصوت")
        await db.inc(c.from_user.id,"audio_conversions"); Path(path).unlink(missing_ok=True); Path(a).unlink(missing_ok=True)
    except Exception: await c.message.answer("❌ تعذر تحميل الصوت.")

async def send_youtube(m,q):
    await m.answer("⏳ جارٍ البحث في YouTube...")
    await results_youtube(m,await downloader.youtube_search(q))

async def results_youtube(m,items):
    if not items:return await m.answer("لم يتم العثور على نتائج.")
    for x in items[:10]:
        token=secrets.token_urlsafe(9); CACHE[token]={"url":x.url,"platform":"youtube"}; cap=f"▶️ YouTube\n🎬 {x.title}\n{x.meta}"
        if x.thumb:
            try: await m.answer_photo(x.thumb,caption=cap,reply_markup=youtube(token))
            except: await m.answer(cap,reply_markup=youtube(token))
        else: await m.answer(cap,reply_markup=youtube(token))

@dp.callback_query(F.data.startswith("admin:"))
async def admin_cb(c):
    if c.from_user.id!=S.admin_id:return await c.answer("غير مصرح",show_alert=True)
    await c.answer(); a=c.data.split(":",1)[1]
    if a=="users":
        rows=await db.users(); p=Path("users.txt"); p.write_text("\n".join(f"{u.telegram_id} | {u.first_name or ''} | @{u.username or '-'}" for u in rows),encoding="utf-8")
        await c.message.answer_document(FSInputFile(p)); p.unlink(missing_ok=True)
    elif a=="stats":
        n,d,aud,plat=await db.stats(); top="\n".join(f"• {p or 'unknown'}: {v}" for p,v in plat) or "لا توجد بيانات"
        await c.message.answer(f"📊 الإحصائيات\n\n👥 المستخدمون: {n}\n📥 التحميلات: {d}\n🎵 التحويلات: {aud}\n\n🔥 المنصات:\n{top}")
    elif a=="broadcast": ADMIN_MODE[c.from_user.id]="broadcast"; await c.message.answer("📢 أرسل الرسالة:")
    elif a=="user": ADMIN_MODE[c.from_user.id]="user"; await c.message.answer("🔎 أرسل Telegram ID:")

@dp.callback_query(F.data.startswith(("ban:","unban:","notify:")))
async def user_action(c):
    if c.from_user.id!=S.admin_id:return await c.answer("غير مصرح",show_alert=True)
    a,tid=c.data.split(":"); tid=int(tid); u=await db.get(tid)
    if not u:return await c.answer("المستخدم غير موجود",show_alert=True)
    if a=="notify": ADMIN_MODE[c.from_user.id]=f"notify:{tid}"; await c.message.answer("📩 أرسل الرسالة:")
    else:
        async with db.sessions() as s:
            from sqlalchemy import select
            obj=(await s.execute(select(__import__("database").User).where(__import__("database").User.telegram_id==tid))).scalar_one()
            obj.is_banned=a=="ban"; await s.commit()
        await c.message.answer("✅ تم تحديث الحالة.",reply_markup=user_admin(tid))
    await c.answer()

async def admin_text(m):
    mode=ADMIN_MODE.pop(m.from_user.id,None)
    if mode=="broadcast":
        n=0
        for u in await db.users():
            if u.is_banned:continue
            try: await bot.copy_message(u.telegram_id,m.chat.id,m.message_id); n+=1
            except:pass
        await m.answer(f"✅ تم الإرسال إلى {n} مستخدم.")
    elif mode=="user" and (m.text or "").isdigit():
        u=await db.get(int(m.text))
        if not u:return await m.answer("المستخدم غير موجود.")
        await m.answer(f"👤 {u.first_name or ''}\n@{u.username or '-'}\nID: {u.telegram_id}\n📥 {u.downloads}\n🎵 {u.audio_conversions}\n{'🚫 محظور' if u.is_banned else '🟢 نشط'}",reply_markup=user_admin(u.telegram_id))
    elif mode and mode.startswith("notify:"):
        tid=int(mode.split(":")[1])
        try: await bot.copy_message(tid,m.chat.id,m.message_id); await m.answer("✅ تم الإرسال.")
        except: await m.answer("❌ تعذر الإرسال.")

async def main():
    await db.init(); Path(S.download_dir).mkdir(exist_ok=True); await dp.start_polling(bot)

if __name__=="__main__": asyncio.run(main())
