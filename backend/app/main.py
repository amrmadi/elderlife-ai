import random
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from .risk import assess, LEVELS, NEXT_STEP

engine = create_engine("sqlite:///./elderlife.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
now = datetime.utcnow

class Elderly(Base):
    __tablename__ = "elderly"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    age = Column(Integer)
    baseline_activity = Column(Float, default=50)

class CheckIn(Base):
    __tablename__ = "checkins"
    id = Column(Integer, primary_key=True)
    elderly_id = Column(Integer, index=True)
    scheduled_at = Column(DateTime)
    responded_at = Column(DateTime, nullable=True)

class Event(Base):  # kind: activity | fall | ok
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    elderly_id = Column(Integer, index=True)
    kind = Column(String)
    value = Column(Float, default=0)
    created_at = Column(DateTime, default=now)

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    elderly_id = Column(Integer, index=True)
    level = Column(String)
    reasons = Column(String)
    status = Column(String, default="open")  # open | acknowledged
    created_at = Column(DateTime, default=now)

class CarePlanItem(Base):  # reminders only: recorded plan, no diagnosis or dose changes
    __tablename__ = "careplan"
    id = Column(Integer, primary_key=True)
    elderly_id = Column(Integer, index=True)
    kind = Column(String)  # medication | meal | water | activity
    title = Column(String)
    time = Column(String)  # HH:MM
    note = Column(String, default="")
    done_date = Column(String, nullable=True)  # YYYY-MM-DD of last completion

Base.metadata.create_all(engine)
app = FastAPI(title="ElderLife AI API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def is_overdue(i, grace_min=30):
    """Reminder time (HH:MM, server local time) passed by more than grace_min and not done today."""
    t = datetime.now()
    if i.done_date == t.strftime("%Y-%m-%d"): return False
    h, m = map(int, i.time.split(":"))
    return t > t.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(minutes=grace_min)

def signals(db, e):
    t = now()
    ci = db.query(CheckIn).filter_by(elderly_id=e.id).order_by(CheckIn.scheduled_at.desc()).first()
    delay = max(0, ((ci.responded_at or t) - ci.scheduled_at).total_seconds() / 60) if ci else 0
    acts = [x.value for x in db.query(Event).filter(Event.elderly_id == e.id, Event.kind == "activity", Event.created_at > t - timedelta(hours=3))]
    ratio = (sum(acts) / len(acts)) / e.baseline_activity if acts else None
    fall = db.query(Event).filter(Event.elderly_id == e.id, Event.kind == "fall", Event.created_at > t - timedelta(hours=2)).order_by(Event.created_at.desc()).first()
    answered = bool(fall and db.query(Event).filter(Event.elderly_id == e.id, Event.kind == "ok", Event.created_at > fall.created_at).first())
    missed = sum(is_overdue(i) for i in db.query(CarePlanItem).filter_by(elderly_id=e.id))
    return {"checkin_delay_min": round(delay), "activity_ratio": ratio, "fall": bool(fall),
            "fall_answered": answered, "missed_reminders": missed}

def evaluate(db, e):
    s = signals(db, e)
    r = assess(s)
    if r["level"] in ("High", "Critical"):
        open_same = db.query(Alert).filter_by(elderly_id=e.id, level=r["level"], status="open").first()
        if not open_same:
            db.add(Alert(elderly_id=e.id, level=r["level"], reasons="; ".join(r["reasons"])))
            db.commit()
    r["next_step"] = NEXT_STEP.get(r["level"])
    return {**r, "signals": s}

class NewElderly(BaseModel):
    name: str
    age: int | None = None
    baseline_activity: float = 50

class NewEvent(BaseModel):
    elderly_id: int
    kind: str
    value: float = 0

@app.get("/elderly")
def list_elderly(db=Depends(get_db)):
    out = []
    for e in db.query(Elderly).all():
        r = evaluate(db, e)
        out.append({"id": e.id, "name": e.name, "age": e.age, "level": r["level"], "score": r["score"], "reasons": r["reasons"]})
    return sorted(out, key=lambda x: -x["score"])

@app.post("/elderly")
def create_elderly(body: NewElderly, db=Depends(get_db)):
    e = Elderly(**body.model_dump()); db.add(e); db.flush()
    db.add(CheckIn(elderly_id=e.id, scheduled_at=now())); db.commit()
    return {"id": e.id}

@app.get("/elderly/{eid}")
def get_elderly(eid: int, db=Depends(get_db)):
    e = db.get(Elderly, eid)
    if not e: raise HTTPException(404, "Person not found")
    events = db.query(Event).filter_by(elderly_id=eid).order_by(Event.created_at.desc()).limit(10).all()
    return {"id": e.id, "name": e.name, "age": e.age, "baseline_activity": e.baseline_activity,
            "risk": evaluate(db, e),
            "events": [{"kind": x.kind, "value": x.value, "at": x.created_at.isoformat()} for x in events]}

@app.post("/elderly/{eid}/checkin")
def checkin(eid: int, db=Depends(get_db)):
    ci = db.query(CheckIn).filter_by(elderly_id=eid, responded_at=None).order_by(CheckIn.scheduled_at.desc()).first()
    if not ci:
        ci = CheckIn(elderly_id=eid, scheduled_at=now()); db.add(ci)
    ci.responded_at = now(); db.commit()
    return {"ok": True}

@app.post("/events")
def add_event(body: NewEvent, db=Depends(get_db)):
    if body.kind not in ("activity", "fall", "ok"): raise HTTPException(400, "kind must be activity, fall or ok")
    db.add(Event(**body.model_dump())); db.commit()
    e = db.get(Elderly, body.elderly_id)
    if e and body.kind == "ok":  # person answered "I'm OK": close open alerts
        for a in db.query(Alert).filter_by(elderly_id=e.id, status="open"): a.status = "acknowledged"
        db.commit()
    return evaluate(db, e) if e else {}

class NewItem(BaseModel):
    kind: str
    title: str
    time: str
    note: str = ""

def item_out(i):
    return {"id": i.id, "kind": i.kind, "title": i.title, "time": i.time, "note": i.note,
            "done_today": i.done_date == now().strftime("%Y-%m-%d"), "overdue": is_overdue(i)}

@app.get("/elderly/{eid}/careplan")
def get_plan(eid: int, db=Depends(get_db)):
    rows = db.query(CarePlanItem).filter_by(elderly_id=eid).order_by(CarePlanItem.time).all()
    return [item_out(i) for i in rows]

@app.post("/elderly/{eid}/careplan")
def add_item(eid: int, body: NewItem, db=Depends(get_db)):
    if body.kind not in ("medication", "meal", "water", "activity"): raise HTTPException(400, "Invalid kind")
    db.add(CarePlanItem(elderly_id=eid, **body.model_dump())); db.commit()
    return {"ok": True}

@app.post("/careplan/{iid}/done")
def mark_done(iid: int, db=Depends(get_db)):
    i = db.get(CarePlanItem, iid)
    if not i: raise HTTPException(404, "Item not found")
    today = now().strftime("%Y-%m-%d")
    i.done_date = None if i.done_date == today else today  # toggle
    db.commit()
    return item_out(i)

@app.delete("/careplan/{iid}")
def delete_item(iid: int, db=Depends(get_db)):
    i = db.get(CarePlanItem, iid)
    if i: db.delete(i); db.commit()
    return {"ok": True}

@app.get("/alerts")
def alerts(db=Depends(get_db)):
    names = {e.id: e.name for e in db.query(Elderly)}
    rows = db.query(Alert).order_by(Alert.created_at.desc()).limit(50).all()
    return [{"id": a.id, "elderly_id": a.elderly_id, "name": names.get(a.elderly_id), "level": a.level,
             "reasons": a.reasons, "status": a.status, "created_at": a.created_at.isoformat()} for a in rows]

@app.post("/alerts/{aid}/ack")
def ack(aid: int, db=Depends(get_db)):
    a = db.get(Alert, aid)
    if not a: raise HTTPException(404, "Alert not found")
    a.status = "acknowledged"; db.commit()
    return {"ok": True}

@app.post("/simulate/seed")
def seed(db=Depends(get_db)):
    """Synthetic demo data (not real people)."""
    for m in (Alert, Event, CheckIn, CarePlanItem, Elderly): db.query(m).delete()
    names = ["Hoda Mahmoud", "Samir Fathy", "Nadia Ibrahim", "Abdel Rahman Ali", "Layla Hassan", "Mostafa Kamel",
             "Fatma Zaki", "Youssef Adel", "Salwa Naguib", "Ahmed Sherif", "Mona Said", "Kamal Aboud"]
    for n in names:
        e = Elderly(name=n, age=random.randint(68, 90)); db.add(e); db.flush()
        for kind, title, t in [("medication", "Morning medication (as prescribed)", "08:00"), ("meal", "Breakfast", "09:30"),
                               ("water", "Glass of water", "11:00"), ("activity", "Short walk", "17:00")]:
            db.add(CarePlanItem(elderly_id=e.id, kind=kind, title=title, time=t))
        sc = random.choices(["ok", "late", "inactive", "fall"], [6, 2, 2, 2])[0]
        if sc == "ok":  # healthy demo people completed today's reminders
            for it in db.query(CarePlanItem).filter_by(elderly_id=e.id): it.done_date = datetime.now().strftime("%Y-%m-%d")
        sched = now() - timedelta(minutes=60 if sc == "ok" else 180)
        db.add(CheckIn(elderly_id=e.id, scheduled_at=sched, responded_at=sched + timedelta(minutes=8) if sc == "ok" else None))
        for i in range(6):
            v = random.uniform(40, 60) if sc in ("ok", "late") else random.uniform(5, 20)
            db.add(Event(elderly_id=e.id, kind="activity", value=v, created_at=now() - timedelta(minutes=25 * i + 5)))
        if sc == "fall": db.add(Event(elderly_id=e.id, kind="fall", created_at=now() - timedelta(minutes=10)))
    db.commit()
    for e in db.query(Elderly): evaluate(db, e)
    return {"seeded": len(names)}
