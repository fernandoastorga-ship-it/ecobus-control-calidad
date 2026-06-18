import os
import io
import csv
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import qrcode
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, ForeignKey, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = STATIC_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ecobus_calidad.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
WHATSAPP_URL = os.getenv("WHATSAPP_URL", "https://wa.me/56999990054")
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://www.ecobus.cl")
INSTAGRAM_URL = os.getenv("INSTAGRAM_URL", "https://instagram.com/ecobus.cl")

app = FastAPI(title="Control de Calidad de Conducción Ecobus")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

class Driver(Base):
    __tablename__ = "drivers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(160), nullable=False)
    phone = Column(String(80), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    buses = relationship("Bus", back_populates="driver")

class Bus(Base):
    __tablename__ = "buses"
    id = Column(Integer, primary_key=True, index=True)
    internal_number = Column(String(80), nullable=False)
    plate = Column(String(40), nullable=False)
    bus_type = Column(String(80), nullable=True)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    driver = relationship("Driver", back_populates="buses")
    reviews = relationship("Review", back_populates="bus")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("drivers.id"), nullable=True)
    qr_type = Column(String(20), nullable=False)  # interior/exterior
    rating = Column(Integer, nullable=False)
    observation_type = Column(String(30), nullable=False, default="Sugerencia")
    comment = Column(Text, nullable=True)
    passenger_name = Column(String(160), nullable=True)
    anonymous = Column(Boolean, default=False)
    photo_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(80), nullable=True)
    user_agent = Column(Text, nullable=True)
    bus = relationship("Bus", back_populates="reviews")
    driver = relationship("Driver")

class ClickEvent(Base):
    __tablename__ = "click_events"
    id = Column(Integer, primary_key=True, index=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False)
    qr_type = Column(String(20), nullable=False)
    action = Column(String(40), nullable=False)  # whatsapp/web/instagram
    created_at = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(80), nullable=True)
    user_agent = Column(Text, nullable=True)
    bus = relationship("Bus")

Base.metadata.create_all(bind=engine)

def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def is_admin(request: Request) -> bool:
    return request.cookies.get("ecobus_admin") == "ok"

def require_admin(request: Request):
    if not is_admin(request):
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})

def base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def normalize_observation_type(value: str) -> str:
    value = (value or "").strip().lower()
    if "fel" in value:
        return "Felicitación"
    if "recl" in value:
        return "Reclamo"
    return "Sugerencia"

def build_driver_rankings(db: Session):
    drivers = db.query(Driver).order_by(Driver.name.asc()).all()
    ranking = []
    for d in drivers:
        q = db.query(Review).filter(Review.driver_id == d.id)
        total = q.count()
        avg = q.with_entities(func.avg(Review.rating)).scalar() or 0
        felicitaciones = q.filter(Review.observation_type == "Felicitación").count()
        sugerencias = q.filter(Review.observation_type == "Sugerencia").count()
        reclamos = q.filter(Review.observation_type == "Reclamo").count()
        fotos = q.filter(Review.photo_path.isnot(None)).count()
        interior = q.filter(Review.qr_type == "interior").count()
        exterior = q.filter(Review.qr_type == "exterior").count()
        buses_actuales = ", ".join([f"{b.internal_number} ({b.plate})" for b in d.buses]) or "Sin bus asignado"
        # Puntaje de gestión: premia felicitaciones y nota; penaliza reclamos.
        score = (avg * 20) + (felicitaciones * 3) + (sugerencias * 1) - (reclamos * 4)
        ranking.append({
            "driver": d, "total": total, "avg": avg, "felicitaciones": felicitaciones,
            "sugerencias": sugerencias, "reclamos": reclamos, "fotos": fotos,
            "interior": interior, "exterior": exterior, "buses_actuales": buses_actuales,
            "score": score
        })
    ranking.sort(key=lambda x: (x["total"], x["score"], x["avg"], x["felicitaciones"], -x["reclamos"]), reverse=True)
    return ranking

@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/admin")

@app.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/admin/login")
def login(password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        return RedirectResponse("/admin/login?error=1", status_code=303)
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie("ecobus_admin", "ok", httponly=True, samesite="lax")
    return response

@app.get("/admin/logout")
def logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie("ecobus_admin")
    return response

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(db_session)):
    require_admin(request)
    buses = db.query(Bus).order_by(Bus.id.desc()).all()
    drivers = db.query(Driver).order_by(Driver.name.asc()).all()
    reviews = db.query(Review).order_by(Review.created_at.desc()).limit(50).all()
    total_reviews = db.query(Review).count()
    avg_rating = db.query(func.avg(Review.rating)).scalar() or 0
    total_clicks = db.query(ClickEvent).count()
    rows = []
    for bus in buses:
        avg = db.query(func.avg(Review.rating)).filter(Review.bus_id == bus.id).scalar() or 0
        n = db.query(Review).filter(Review.bus_id == bus.id).count()
        clicks = db.query(ClickEvent).filter(ClickEvent.bus_id == bus.id).count()
        rows.append({"bus": bus, "avg": avg, "reviews": n, "clicks": clicks})
    driver_rankings = build_driver_rankings(db)
    return templates.TemplateResponse("admin.html", {
        "request": request, "buses": buses, "drivers": drivers, "reviews": reviews,
        "total_reviews": total_reviews, "avg_rating": avg_rating, "total_clicks": total_clicks,
        "rows": rows, "driver_rankings": driver_rankings, "base_url": base_url(request)
    })

@app.post("/admin/buses")
def add_bus(request: Request, internal_number: str = Form(...), plate: str = Form(...), bus_type: str = Form("Bus"), driver_id: Optional[int] = Form(None), db: Session = Depends(db_session)):
    require_admin(request)
    bus = Bus(internal_number=internal_number.strip(), plate=plate.strip().upper(), bus_type=bus_type.strip(), driver_id=driver_id or None)
    db.add(bus); db.commit()
    return RedirectResponse("/admin#buses", status_code=303)

@app.post("/admin/buses/{bus_id}/delete")
def delete_bus(bus_id: int, request: Request, db: Session = Depends(db_session)):
    require_admin(request)
    bus = db.get(Bus, bus_id)
    if bus:
        db.delete(bus); db.commit()
    return RedirectResponse("/admin#buses", status_code=303)

@app.post("/admin/drivers")
def add_driver(request: Request, name: str = Form(...), phone: str = Form(""), db: Session = Depends(db_session)):
    require_admin(request)
    db.add(Driver(name=name.strip(), phone=phone.strip() or None)); db.commit()
    return RedirectResponse("/admin#drivers", status_code=303)

@app.post("/admin/assign")
def assign_driver(request: Request, bus_id: int = Form(...), driver_id: Optional[int] = Form(None), db: Session = Depends(db_session)):
    require_admin(request)
    bus = db.get(Bus, bus_id)
    if bus:
        bus.driver_id = driver_id or None
        db.commit()
    return RedirectResponse("/admin#buses", status_code=303)

@app.get("/admin/drivers/{driver_id}", response_class=HTMLResponse)
def driver_detail(driver_id: int, request: Request, db: Session = Depends(db_session)):
    require_admin(request)
    driver = db.get(Driver, driver_id)
    if not driver:
        raise HTTPException(404)
    reviews = db.query(Review).filter(Review.driver_id == driver.id).order_by(Review.created_at.desc()).all()
    total = len(reviews)
    avg_rating = db.query(func.avg(Review.rating)).filter(Review.driver_id == driver.id).scalar() or 0
    felicitaciones = db.query(Review).filter(Review.driver_id == driver.id, Review.observation_type == "Felicitación").count()
    sugerencias = db.query(Review).filter(Review.driver_id == driver.id, Review.observation_type == "Sugerencia").count()
    reclamos = db.query(Review).filter(Review.driver_id == driver.id, Review.observation_type == "Reclamo").count()
    interior = db.query(Review).filter(Review.driver_id == driver.id, Review.qr_type == "interior").count()
    exterior = db.query(Review).filter(Review.driver_id == driver.id, Review.qr_type == "exterior").count()
    by_bus = []
    bus_ids = sorted({r.bus_id for r in reviews})
    for bus_id in bus_ids:
        bus = db.get(Bus, bus_id)
        if not bus:
            continue
        q = db.query(Review).filter(Review.driver_id == driver.id, Review.bus_id == bus_id)
        by_bus.append({
            "bus": bus, "total": q.count(),
            "avg": q.with_entities(func.avg(Review.rating)).scalar() or 0,
            "felicitaciones": q.filter(Review.observation_type == "Felicitación").count(),
            "sugerencias": q.filter(Review.observation_type == "Sugerencia").count(),
            "reclamos": q.filter(Review.observation_type == "Reclamo").count(),
        })
    return templates.TemplateResponse("driver_detail.html", {
        "request": request, "driver": driver, "reviews": reviews, "total": total,
        "avg_rating": avg_rating, "felicitaciones": felicitaciones, "sugerencias": sugerencias,
        "reclamos": reclamos, "interior": interior, "exterior": exterior, "by_bus": by_bus
    })

@app.get("/admin/export/reviews.csv")
def export_reviews(request: Request, db: Session = Depends(db_session)):
    require_admin(request)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id","fecha_hora","bus","patente","conductor","qr_tipo","estrellas","tipo_observacion","comentario","nombre","anonimo","foto"])
    for r in db.query(Review).order_by(Review.created_at.desc()).all():
        writer.writerow([r.id, r.created_at.isoformat(), r.bus.internal_number, r.bus.plate, r.driver.name if r.driver else "", r.qr_type, r.rating, r.observation_type, r.comment or "", r.passenger_name or "", r.anonymous, r.photo_path or ""])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=evaluaciones_ecobus.csv"})

@app.get("/qr/{bus_id}/{qr_type}", response_class=HTMLResponse)
def qr_landing(bus_id: int, qr_type: str, request: Request, db: Session = Depends(db_session)):
    if qr_type not in ["interior", "exterior"]:
        raise HTTPException(404)
    bus = db.get(Bus, bus_id)
    if not bus:
        raise HTTPException(404)
    return templates.TemplateResponse("landing.html", {"request": request, "bus": bus, "qr_type": qr_type})

@app.post("/qr/{bus_id}/{qr_type}/review")
async def submit_review(bus_id: int, qr_type: str, request: Request, rating: int = Form(...), observation_type: str = Form("Sugerencia"), comment: str = Form(""), passenger_name: str = Form(""), anonymous: Optional[str] = Form(None), photo: Optional[UploadFile] = File(None), db: Session = Depends(db_session)):
    bus = db.get(Bus, bus_id)
    if not bus or qr_type not in ["interior", "exterior"]:
        raise HTTPException(404)
    if rating < 1 or rating > 5:
        raise HTTPException(400, "Calificación inválida")
    photo_path = None
    if photo and photo.filename:
        ext = Path(photo.filename).suffix.lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp", ".heic"]:
            raise HTTPException(400, "Formato de foto no permitido")
        safe_name = f"review_{bus_id}_{secrets.token_hex(8)}{ext}"
        dest = UPLOAD_DIR / safe_name
        content = await photo.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(400, "La foto supera 10 MB")
        dest.write_bytes(content)
        photo_path = f"/static/uploads/{safe_name}"
    observation_type = normalize_observation_type(observation_type)
    rev = Review(bus_id=bus.id, driver_id=bus.driver_id, qr_type=qr_type, rating=rating, observation_type=observation_type, comment=comment.strip() or None, passenger_name=None if anonymous else (passenger_name.strip() or None), anonymous=bool(anonymous), photo_path=photo_path, ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"))
    db.add(rev); db.commit()
    return templates.TemplateResponse("thanks.html", {"request": request, "bus": bus})

@app.get("/go/{bus_id}/{qr_type}/{action}")
def commercial_click(bus_id: int, qr_type: str, action: str, request: Request, db: Session = Depends(db_session)):
    bus = db.get(Bus, bus_id)
    if not bus or qr_type not in ["interior","exterior"] or action not in ["whatsapp","web","instagram"]:
        raise HTTPException(404)
    db.add(ClickEvent(bus_id=bus.id, qr_type=qr_type, action=action, ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent")))
    db.commit()
    target = {"whatsapp": WHATSAPP_URL, "web": WEBSITE_URL, "instagram": INSTAGRAM_URL}[action]
    return RedirectResponse(target)

@app.get("/admin/qr/{bus_id}/{qr_type}.png")
def download_qr(bus_id: int, qr_type: str, request: Request, db: Session = Depends(db_session)):
    require_admin(request)
    bus = db.get(Bus, bus_id)
    if not bus or qr_type not in ["interior","exterior"]:
        raise HTTPException(404)
    url = f"{base_url(request)}/qr/{bus.id}/{qr_type}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    filename = f"QR_Ecobus_{bus.internal_number}_{bus.plate}_{qr_type}.png".replace(" ", "_")
    return StreamingResponse(buf, media_type="image/png", headers={"Content-Disposition": f"attachment; filename={quote_plus(filename)}"})
