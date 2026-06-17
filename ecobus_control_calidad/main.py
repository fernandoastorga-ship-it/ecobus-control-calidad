import os
import io
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Request, Depends, Form, File, UploadFile, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Text, LargeBinary, func
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
from starlette.middleware.sessions import SessionMiddleware
import qrcode

APP_NAME = "Control de Calidad de Conducción Ecobus"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
WHATSAPP_URL = os.getenv("WHATSAPP_URL", "https://wa.me/56999990054")
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://www.ecobus.cl")
INSTAGRAM_URL = os.getenv("INSTAGRAM_URL", "https://instagram.com/ecobus.cl")
BASE_URL = os.getenv("BASE_URL", "")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ecobus_calidad.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Bus(Base):
    __tablename__ = "buses"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(60), unique=True, index=True, nullable=False)
    patente = Column(String(30), nullable=False)
    tipo = Column(String(40), default="Bus")
    active = Column(Boolean, default=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    driver = relationship("Driver", back_populates="buses")
    evaluations = relationship("Evaluation", back_populates="bus")
    clicks = relationship("CommercialClick", back_populates="bus")

class Driver(Base):
    __tablename__ = "drivers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(40), default="")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    buses = relationship("Bus", back_populates="driver")

class Evaluation(Base):
    __tablename__ = "evaluations"
    id = Column(Integer, primary_key=True, index=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False)
    driver_name_snapshot = Column(String(120), default="Sin asignar")
    qr_type = Column(String(20), nullable=False)  # interior / exterior
    rating = Column(Integer, nullable=False)
    observation_type = Column(String(30), default="Comentario")
    comment = Column(Text, default="")
    passenger_name = Column(String(120), default="Anónimo")
    anonymous = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    bus = relationship("Bus", back_populates="evaluations")
    photos = relationship("EvaluationPhoto", back_populates="evaluation", cascade="all, delete-orphan")

class EvaluationPhoto(Base):
    __tablename__ = "evaluation_photos"
    id = Column(Integer, primary_key=True, index=True)
    evaluation_id = Column(Integer, ForeignKey("evaluations.id"), nullable=False)
    filename = Column(String(255), default="foto")
    content_type = Column(String(100), default="image/jpeg")
    data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    evaluation = relationship("Evaluation", back_populates="photos")

class CommercialClick(Base):
    __tablename__ = "commercial_clicks"
    id = Column(Integer, primary_key=True, index=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False)
    qr_type = Column(String(20), nullable=False)
    action = Column(String(30), nullable=False)  # whatsapp / instagram / website
    created_at = Column(DateTime, default=datetime.utcnow)
    bus = relationship("Bus", back_populates="clicks")

Base.metadata.create_all(bind=engine)

app = FastAPI(title=APP_NAME)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "ecobus-secret-local"))
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def is_admin(request: Request):
    return request.session.get("admin") is True

def require_admin(request: Request):
    if not is_admin(request):
        raise HTTPException(status_code=307, headers={"Location": "/admin/login"})

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return RedirectResponse("/admin")

@app.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "app_name": APP_NAME})

@app.post("/admin/login")
def login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        request.session["admin"] = True
        return RedirectResponse("/admin", status_code=303)
    return RedirectResponse("/admin/login?error=1", status_code=303)

@app.get("/admin/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login")

@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, db: Session = Depends(db_session)):
    require_admin(request)
    buses = db.query(Bus).order_by(Bus.code).all()
    drivers = db.query(Driver).order_by(Driver.name).all()
    evaluations = db.query(Evaluation).order_by(Evaluation.created_at.desc()).limit(200).all()
    total_evals = db.query(Evaluation).count()
    avg_rating = db.query(func.avg(Evaluation.rating)).scalar() or 0
    clicks = db.query(CommercialClick).count()
    bus_stats = []
    for b in buses:
        evs = b.evaluations
        avg = sum(e.rating for e in evs)/len(evs) if evs else 0
        bus_stats.append({"bus": b, "count": len(evs), "avg": avg, "clicks": len(b.clicks)})
    ranking = sorted(bus_stats, key=lambda x: x["avg"], reverse=True)
    return templates.TemplateResponse("admin.html", {
        "request": request, "app_name": APP_NAME, "buses": buses, "drivers": drivers,
        "evaluations": evaluations, "total_evals": total_evals, "avg_rating": avg_rating,
        "clicks": clicks, "ranking": ranking, "base_url": BASE_URL
    })

@app.post("/admin/buses")
def create_bus(request: Request, code: str = Form(...), patente: str = Form(...), tipo: str = Form("Bus"), driver_id: Optional[int] = Form(None), db: Session = Depends(db_session)):
    require_admin(request)
    bus = Bus(code=code.strip(), patente=patente.strip().upper(), tipo=tipo.strip(), driver_id=driver_id or None)
    db.add(bus); db.commit()
    return RedirectResponse("/admin#buses", status_code=303)

@app.post("/admin/buses/{bus_id}/delete")
def delete_bus(request: Request, bus_id: int, db: Session = Depends(db_session)):
    require_admin(request)
    bus = db.get(Bus, bus_id)
    if bus: db.delete(bus); db.commit()
    return RedirectResponse("/admin#buses", status_code=303)

@app.post("/admin/drivers")
def create_driver(request: Request, name: str = Form(...), phone: str = Form(""), db: Session = Depends(db_session)):
    require_admin(request)
    db.add(Driver(name=name.strip(), phone=phone.strip())); db.commit()
    return RedirectResponse("/admin#drivers", status_code=303)

@app.post("/admin/assign")
def assign_driver(request: Request, bus_id: int = Form(...), driver_id: Optional[int] = Form(None), db: Session = Depends(db_session)):
    require_admin(request)
    bus = db.get(Bus, bus_id)
    if bus:
        bus.driver_id = driver_id or None
        db.commit()
    return RedirectResponse("/admin#buses", status_code=303)

@app.get("/q/{bus_code}/{qr_type}", response_class=HTMLResponse)
def qr_landing(request: Request, bus_code: str, qr_type: str, db: Session = Depends(db_session)):
    if qr_type not in ["interior", "exterior"]:
        raise HTTPException(404)
    bus = db.query(Bus).filter(Bus.code == bus_code).first()
    if not bus:
        return templates.TemplateResponse("not_found.html", {"request": request})
    title = "Experiencia de viaje" if qr_type == "interior" else "Conducción observada"
    return templates.TemplateResponse("landing.html", {"request": request, "bus": bus, "qr_type": qr_type, "title": title, "whatsapp": WHATSAPP_URL, "website": WEBSITE_URL, "instagram": INSTAGRAM_URL})

@app.post("/q/{bus_code}/{qr_type}/evaluate")
async def save_evaluation(bus_code: str, qr_type: str, rating: int = Form(...), observation_type: str = Form("Comentario"), comment: str = Form(""), passenger_name: str = Form(""), anonymous: Optional[str] = Form(None), photos: List[UploadFile] = File(default=[]), db: Session = Depends(db_session)):
    bus = db.query(Bus).filter(Bus.code == bus_code).first()
    if not bus or qr_type not in ["interior", "exterior"]:
        raise HTTPException(404)
    anon = anonymous == "on" or not passenger_name.strip()
    ev = Evaluation(bus_id=bus.id, driver_name_snapshot=bus.driver.name if bus.driver else "Sin asignar", qr_type=qr_type, rating=max(1, min(5, rating)), observation_type=observation_type, comment=comment.strip(), passenger_name="Anónimo" if anon else passenger_name.strip(), anonymous=anon)
    db.add(ev); db.commit(); db.refresh(ev)
    for f in photos[:3]:
        if not f.filename:
            continue
        data = await f.read()
        if data and len(data) <= 10 * 1024 * 1024 and (f.content_type or "").startswith("image/"):
            db.add(EvaluationPhoto(evaluation_id=ev.id, filename=f.filename, content_type=f.content_type, data=data))
    db.commit()
    return RedirectResponse(f"/q/{bus_code}/{qr_type}/gracias", status_code=303)

@app.get("/q/{bus_code}/{qr_type}/gracias", response_class=HTMLResponse)
def thanks(request: Request, bus_code: str, qr_type: str, db: Session = Depends(db_session)):
    bus = db.query(Bus).filter(Bus.code == bus_code).first()
    return templates.TemplateResponse("thanks.html", {"request": request, "bus": bus, "qr_type": qr_type, "whatsapp": WHATSAPP_URL, "website": WEBSITE_URL, "instagram": INSTAGRAM_URL})

@app.get("/go/{bus_code}/{qr_type}/{action}")
def commercial_click(bus_code: str, qr_type: str, action: str, db: Session = Depends(db_session)):
    urls = {"whatsapp": WHATSAPP_URL, "website": WEBSITE_URL, "instagram": INSTAGRAM_URL}
    if action not in urls or qr_type not in ["interior", "exterior"]:
        raise HTTPException(404)
    bus = db.query(Bus).filter(Bus.code == bus_code).first()
    if bus:
        db.add(CommercialClick(bus_id=bus.id, qr_type=qr_type, action=action)); db.commit()
    return RedirectResponse(urls[action])

@app.get("/admin/qr/{bus_id}/{qr_type}.png")
def download_qr(request: Request, bus_id: int, qr_type: str, db: Session = Depends(db_session)):
    require_admin(request)
    bus = db.get(Bus, bus_id)
    if not bus or qr_type not in ["interior", "exterior"]:
        raise HTTPException(404)
    host = BASE_URL.rstrip("/") or str(request.base_url).rstrip("/")
    url = f"{host}/q/{bus.code}/{qr_type}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    filename = f"QR_{bus.code}_{bus.patente}_{qr_type}.png".replace(" ", "_")
    return StreamingResponse(buf, media_type="image/png", headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.get("/admin/photo/{photo_id}")
def view_photo(request: Request, photo_id: int, db: Session = Depends(db_session)):
    require_admin(request)
    p = db.get(EvaluationPhoto, photo_id)
    if not p: raise HTTPException(404)
    return Response(content=p.data, media_type=p.content_type)

@app.get("/health")
def health():
    return {"ok": True}
