# Control de Calidad de Conducción Ecobus

Sistema FastAPI para evaluación de conducción mediante QR interior/exterior por bus, registro de clics comerciales y panel administrador.

## Render

- Runtime: Python
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Variables de entorno

- `ADMIN_PASSWORD`
- `DATABASE_URL`
- `WHATSAPP_URL=https://wa.me/56999990054`
- `WEBSITE_URL=https://www.ecobus.cl`
- `INSTAGRAM_URL=https://instagram.com/ecobus.cl`

## Acceso

- Admin: `/admin`
- Clave local por defecto: `admin123`
