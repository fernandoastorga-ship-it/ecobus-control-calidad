# Control de Calidad de Conducción Ecobus

Sistema FastAPI + PostgreSQL para evaluaciones por QR interior/exterior, ranking de conductores, fotos, clics comerciales y descarga de QR PNG.

## Render

Build Command:
```bash
pip install -r requirements.txt
```

Start Command:
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Variables de entorno:
```text
DATABASE_URL=Internal Database URL de Render PostgreSQL
ADMIN_PASSWORD=tu_clave
WHATSAPP_URL=https://wa.me/56999990054
WEBSITE_URL=https://www.ecobus.cl
INSTAGRAM_URL=https://instagram.com/ecobus.cl
```

## Acceso

Panel admin:
```text
/admin
```

## Mejoras incluidas

- Pestaña Ranking conductores.
- Ranking por cantidad de evaluaciones y desempeño.
- Separación por felicitaciones, sugerencias y reclamos.
- Perfil individual por conductor.
- Evaluaciones separadas por conductor, bus, origen QR, fecha, comentario y foto.
