# Control de Calidad de Conducción Ecobus

Sistema web para Render con FastAPI + PostgreSQL.

## Funciones
- Panel administrador.
- Crear buses y conductores.
- Asignar conductor a bus.
- Generar QR Interior y Exterior por bus.
- Descargar cada QR en PNG.
- Landing pública por QR.
- Evaluación con estrellas, comentario, tipo de observación, nombre/anónimo y fotos opcionales.
- Botones comerciales: WhatsApp, Instagram y sitio web.
- Registro de clics comerciales por bus y tipo de QR.

## Probar localmente

```bash
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn main:app --reload
```

Abrir:

```text
http://127.0.0.1:8000/admin
```

Clave inicial:

```text
admin123
```

## Variables de entorno para Render

```text
DATABASE_URL=URL_DE_POSTGRES_RENDER
ADMIN_PASSWORD=tu_clave_segura
SESSION_SECRET=texto_largo_aleatorio
BASE_URL=https://tu-servicio.onrender.com
WHATSAPP_URL=https://wa.me/56999990054
WEBSITE_URL=https://www.ecobus.cl
INSTAGRAM_URL=https://instagram.com/ecobus.cl
```

## Render

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

## Nota sobre fotos
Las fotos se guardan en la base de datos para evitar problemas de almacenamiento temporal en Render.
