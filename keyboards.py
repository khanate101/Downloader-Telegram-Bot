from urllib.parse import quote
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def platforms(kind, q):
    # Username search only: Instagram or TikTok.
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📷 Instagram", callback_data=f"{kind}:instagram:{q}"),
            InlineKeyboardButton(text="🎵 TikTok", callback_data=f"{kind}:tiktok:{q}")
        ]
    ])

def media(token, url):
    share = f"https://t.me/share/url?url={quote(url, safe='')}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎵 تحويل إلى صوت", callback_data=f"audio:{token}"),
            InlineKeyboardButton(text="🔗 مشاركة", url=share)
        ]
    ])

def result(token):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 تحميل", callback_data=f"result:{token}")]
    ])

def youtube(token):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 تحميل الفيديو", callback_data=f"result:{token}")],
        [InlineKeyboardButton(text="🎵 تحميل الصوت", callback_data=f"ytaudio:{token}")]
    ])

def admin():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 إرسال للمستخدمين", callback_data="admin:broadcast"),
            InlineKeyboardButton(text="📥 بيانات المستخدمين", callback_data="admin:users")
        ],
        [
            InlineKeyboardButton(text="🔎 بحث عن مستخدم", callback_data="admin:user"),
            InlineKeyboardButton(text="📊 الإحصائيات", callback_data="admin:stats")
        ]
    ])

def user_admin(tid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚫 حظر", callback_data=f"ban:{tid}"),
            InlineKeyboardButton(text="✅ فك الحظر", callback_data=f"unban:{tid}")
        ],
        [InlineKeyboardButton(text="📩 إشعار خاص", callback_data=f"notify:{tid}")]
    ])
