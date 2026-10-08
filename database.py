from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, String, Text, select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__="users"
    id:Mapped[int]=mapped_column(primary_key=True)
    telegram_id:Mapped[int]=mapped_column(Integer,unique=True,index=True)
    username:Mapped[str|None]=mapped_column(String(255))
    first_name:Mapped[str|None]=mapped_column(String(255))
    last_name:Mapped[str|None]=mapped_column(String(255))
    joined_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
    last_activity:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
    is_banned:Mapped[bool]=mapped_column(Boolean,default=False)
    downloads:Mapped[int]=mapped_column(Integer,default=0)
    audio_conversions:Mapped[int]=mapped_column(Integer,default=0)

class Event(Base):
    __tablename__="events"
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(Integer,index=True)
    event_type:Mapped[str]=mapped_column(String(50),index=True)
    platform:Mapped[str|None]=mapped_column(String(50),index=True)
    query:Mapped[str|None]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))

class Database:
    def __init__(self):
        self.engine=create_async_engine("sqlite+aiosqlite:///bot.db")
        self.sessions=async_sessionmaker(self.engine,expire_on_commit=False)
    async def init(self):
        async with self.engine.begin() as c: await c.run_sync(Base.metadata.create_all)
    async def user(self,tg):
        async with self.sessions() as s:
            u=(await s.execute(select(User).where(User.telegram_id==tg.id))).scalar_one_or_none()
            now=datetime.now(timezone.utc)
            if not u:
                u=User(telegram_id=tg.id,username=tg.username,first_name=tg.first_name,last_name=tg.last_name)
                s.add(u)
            else:
                u.username=tg.username; u.first_name=tg.first_name; u.last_name=tg.last_name; u.last_activity=now
            await s.commit(); return u
    async def get(self,tid):
        async with self.sessions() as s: return (await s.execute(select(User).where(User.telegram_id==tid))).scalar_one_or_none()
    async def inc(self,tid,field):
        async with self.sessions() as s:
            u=(await s.execute(select(User).where(User.telegram_id==tid))).scalar_one()
            setattr(u,field,getattr(u,field)+1); await s.commit()
    async def event(self,uid,kind,platform=None,query=None):
        async with self.sessions() as s: s.add(Event(user_id=uid,event_type=kind,platform=platform,query=query)); await s.commit()
    async def users(self):
        async with self.sessions() as s: return list((await s.execute(select(User).order_by(User.joined_at))).scalars())
    async def stats(self):
        async with self.sessions() as s:
            n=await s.scalar(select(func.count(User.id))) or 0
            d=await s.scalar(select(func.sum(User.downloads))) or 0
            a=await s.scalar(select(func.sum(User.audio_conversions))) or 0
            p=(await s.execute(select(Event.platform,func.count(Event.id)).where(Event.event_type=="download").group_by(Event.platform).order_by(func.count(Event.id).desc()))).all()
            return n,d,a,p
