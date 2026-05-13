# Facturama Portal

Portal web interno para gestión de CFDIs usando la API de Facturama (sandbox). Permite administrar emisores, clientes, productos, facturas electrónicas y generar reportes fiscales consolidados con exportación PDF.

## Stack

- **Backend:** Python 3.10+, Flask 3.x, SQLite
- **Frontend:** Jinja2 templates, Chart.js, CSS moderno (estilo Linear/Stripe)
- **PDF:** WeasyPrint (HTML → PDF), Matplotlib (gráficas estáticas para PDF)
- **API:** Facturama SDK (`facturama>=2.0.0`)
- **Tests:** pytest

## Requisitos

- Python 3.10 o superior
- pip / venv
- Credenciales de Facturama (sandbox o producción)
- Para PDFs: dependencias del sistema de WeasyPrint (ver abajo)

### Dependencias del sistema para WeasyPrint (PDF)

```bash
# Ubuntu/Debian
sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev libcairo2

# macOS
brew install pango gdk-pixbuf

# Fedora
sudo dnf install pango gdk-pixbuf2
```

## Instalación

```bash
# 1. Clonar el repo
git clone https://github.com/IvanJS17/facturama-portal.git
cd facturama-portal

# 2. Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 3. Instalar dependencias
pip install -e ".[dev]"

# 4. Configurar variables de entorno
cp .env.example .env  # Si existe .env.example
# O crea .env manualmente (ver sección Configuración)
```

## Configuración

Crear archivo `.env` en la raíz del proyecto:

```env
# Facturama API (sandbox)
FACTURAMA_USER=tu_usuario_sandbox
FACTURAMA_PASSWORD=tu_password_sandbox
FACTURAMA_API_URL=https://apisandbox.facturama.mx/

# Flask
FLASK_APP=src.app
FLASK_ENV=development
SECRET_KEY=cambia-esto-en-produccion

# Base de datos
DATABASE_URL=sqlite:///facturama_portal.db
```

Para producción, cambiar `FACTURAMA_API_URL` a `https://api.facturama.mx/` y usar credenciales de producción.

## Ejecución

```bash
# Desarrollo (con recarga automática)
flask run --host=0.0.0.0 --port=5000 --reload

# Producción
gunicorn src.app:app --bind 0.0.0.0:5000
```

El portal estará disponible en `http://localhost:5000`.

## Estructura del proyecto

```
facturama-portal/
├── src/
│   ├── app.py                  # Punto de entrada Flask
│   ├── models/
│   │   └── __init__.py         # Esquema SQLite (PortalDatabase)
│   ├── routes/
│   │   ├── common.py           # Helpers compartidos (db, row_or_404)
│   │   ├── dashboard.py        # Dashboard principal
│   │   ├── issuers.py          # CRUD emisores
│   │   ├── clients.py          # CRUD clientes (scoped por emisor)
│   │   ├── products.py         # CRUD productos (scoped por emisor)
│   │   ├── cfdi.py             # CRUD CFDIs + nueva factura
│   │   └── reports.py          # Reportes + API + PDF export
│   ├── services/
│   │   ├── facturama_api.py    # Cliente HTTP Facturama
│   │   ├── facturama_service.py # Orquestación de negocio
│   │   └── reports.py          # ReportService (lógica de agregación)
│   ├── templates/
│   │   ├── base.html           # Layout base
│   │   ├── dashboard.html
│   │   ├── issuers/
│   │   ├── clients/
│   │   ├── products/
│   │   ├── cfdi/
│   │   └── reports/
│   │       ├── index.html              # Selector de reportes
│   │       ├── preview.html            # Vista previa (reportes estándar)
│   │       ├── pdf_template.html       # PDF (reportes estándar)
│   │       ├── emisor_preview.html     # Vista previa consolidada
│   │       └── emisor_pdf_template.html # PDF consolidado
│   ├── static/
│   │   └── styles.css          # Estilos globales
│   └── utils/
│       ├── config.py           # Carga de variables de entorno
│       └── report_graphs.py    # Gráficas Matplotlib para PDF
├── tests/
│   └── unit/                   # Tests unitarios (pytest)
├── scripts/                    # Scripts auxiliares
├── pyproject.toml              # Dependencias y metadata
├── .env                        # Variables de entorno (NO COMMITEAR)
└── README.md
```

## Funcionalidades principales

### Dashboard
- Vista general de CFDIs recientes con emisor, cliente, RFC, folio, total y estatus
- Métricas rápidas

### Emisores
- CRUD de empresas emisoras (RFC, razón social, régimen fiscal)

### Clientes
- CRUD de clientes con scope por emisor (cada cliente pertenece a un solo emisor)
- Listado filtrado por emisor

### Productos
- CRUD de productos con scope por emisor
- Historial de clientes facturados por producto
- Vista de catálogo + productos facturados

### CFDIs
- Listado de facturas con filtros
- Detalle de CFDI con items, impuestos y timbrado
- Nueva factura con flujo guiado por pasos
- Validación: cliente y producto deben pertenecer al emisor seleccionado

### Reportes
- **7 tipos estándar:** Mensual, Semanal, Anual, Personalizado, por Producto, por Cliente, Comparativo
- **Reporte Consolidado por Emisor** (multi-dimensional):
  - 6 tarjetas de resumen (CFDIs, Subtotal, IVA, Total, Cancelados, Promedio)
  - Comparativo con período anterior (% variación)
  - Tendencia mensual (gráfica + tabla)
  - Distribución por producto (gráfica + tabla)
  - Top 5 productos y clientes
  - Desgloses detallados
  - Tabla completa de CFDIs del período
  - 3 modos: Mensual, Trimestral (Q1-Q4), Anual
- Vista previa interactiva con Chart.js
- Exportación PDF profesional con WeasyPrint + Matplotlib

## Tests

```bash
# Ejecutar todos los tests
pytest tests/ -v

# Con cobertura
pytest tests/ -v --cov=src --cov-report=term-missing
```

45 tests cubriendo: rutas, modelos, esquema, validaciones, servicios.

## Notas para agentes AI

Si eres un agente AI trabajando con este proyecto en otra máquina:

1. **Setup mínimo:** Python 3.10+, `pip install -e ".[dev]"`, variables `.env` con credenciales Facturama
2. **El servidor se corre con:** `flask run --host=0.0.0.0 --port=5000` desde la raíz del proyecto
3. **La BD es SQLite:** se crea automáticamente en `facturama_portal.db` al iniciar la app
4. **Las plantillas están en `src/templates/`** con Jinja2. El layout base es `base.html`
5. **Los reportes usan `src/services/reports.py`** → `ReportService.build_report(issuer_id, report_type, params)`
6. **Los PDFs usan WeasyPrint** — requiere dependencias del sistema (ver sección arriba)
7. **El CSS está en `src/static/styles.css`** — diseño moderno Linear/Stripe
8. **No modifiques `src/templates/reports/`** sin revisar el skill de facturama primero
9. **Convención importante:** cada cliente pertenece a exactamente un emisor. Las facturas deben validar que `cliente.emisor == emisor seleccionado`
10. **Los tests son la verdad:** si `pytest tests/ -v` pasa, el código es correcto

### Comandos rápidos

```bash
# Iniciar
source .venv/bin/activate && flask run --host=0.0.0.0 --port=5000

# Test rápido
pytest tests/ -v --tb=short

# Ver rutas registradas
flask routes

# Shell interactivo con contexto Flask
flask shell
```

## Puesta en producción

Esta guía cubre el proceso completo para migrar de sandbox a producción, tanto para humanos como para agentes AI. Asume que el proyecto ya está clonado y las dependencias instaladas según la sección de Instalación.

---

### Para humanos

#### 1. Archivo `.env` de producción

Reemplazar las credenciales de sandbox por las de producción:

```env
# Facturama API (PRODUCCIÓN)
FACTURAMA_USER=tu_usuario_produccion
FACTURAMA_PASSWORD=tu_password_produccion
FACTURAMA_API_URL=https://api.facturama.mx/

# Flask
FLASK_APP=src.app
FLASK_ENV=production
SECRET_KEY=<genera-un-valor-aleatorio-de-al-menos-32-caracteres>
```

Para generar un `SECRET_KEY` seguro:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**Importante:** La URL cambia de `apisandbox.facturama.mx` a `api.facturama.mx`. Las credenciales de sandbox NO funcionan en producción (y viceversa). Si no tienes credenciales de producción, créalas desde el panel de Facturama.

#### 2. Verificar la base de datos

La BD de sandbox (`facturama_portal.db`) contiene datos de prueba. En producción tienes dos opciones:

- **Opción A — Empezar limpio:** borrar `facturama_portal.db` y dejar que la app la cree vacía al iniciar
- **Opción B — Migrar datos:** respaldar la BD anterior y usar los scripts en `scripts/` para poblar emisores y clientes reales

#### 3. Ejecutar con Gunicorn (servidor WSGI)

En producción NO uses `flask run`. Usa Gunicorn:

```bash
# Desde la raíz del proyecto, con el venv activado
gunicorn src.app:app \
    --bind 0.0.0.0:5000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile /var/log/facturama/access.log \
    --error-logfile /var/log/facturama/error.log
```

Parámetros recomendados:
- `--workers 4`: 4 procesos worker (ajusta según CPUs disponibles)
- `--timeout 120`: timeout de 2 minutos (útil para generación de PDFs pesados)
- `--access-logfile` y `--error-logfile`: logs separados para diagnóstico

#### 4. Systemd (servicio permanente)

Para que el portal se ejecute como servicio del sistema y se reinicie automáticamente:

```ini
# /etc/systemd/system/facturama-portal.service
[Unit]
Description=Facturama Portal
After=network.target

[Service]
User=tu-usuario
WorkingDirectory=/ruta/a/facturama-portal
EnvironmentFile=/ruta/a/facturama-portal/.env
ExecStart=/ruta/a/facturama-portal/.venv/bin/gunicorn src.app:app --bind 0.0.0.0:5000 --workers 4 --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Activar e iniciar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable facturama-portal
sudo systemctl start facturama-portal
sudo systemctl status facturama-portal
```

#### 5. Firewall

Si el portal va a ser accesible desde otras máquinas en la red:

```bash
# Permitir puerto 5000 solo en red local (ajusta la subred según tu caso)
sudo ufw allow from 192.168.1.0/24 to any port 5000
```

#### 6. HTTPS (opcional pero recomendado)

Para exponer el portal a internet, usa un reverse proxy con HTTPS:

```bash
# Nginx como reverse proxy
sudo apt install nginx certbot python3-certbot-nginx
```

Configuración básica de Nginx (`/etc/nginx/sites-available/facturama`):

```nginx
server {
    listen 443 ssl;
    server_name facturama.tu-dominio.com;

    ssl_certificate     /etc/letsencrypt/live/facturama.tu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/facturama.tu-dominio.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### 7. Verificación final

```bash
# Tests
pytest tests/ -v --tb=short

# Health check HTTP
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/
# Debe devolver 200

# Verificar que carga el dashboard
curl -s http://localhost:5000/ | grep -o '<title>.*</title>'
# Debe mostrar: <title>Dashboard — Facturama Portal</title>
```

---

### Para agentes AI

Si eres un agente AI encargado de poner este proyecto en producción en una máquina nueva, sigue esta checklist en orden.

#### Checklist de producción

 ```
[ ] 1. Leer README.md completo (sección Instalación primero)
[ ] 2. Verificar Python:     python3 --version          # ≥ 3.10
[ ] 3. Verificar sistema:    sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev libcairo2
[ ] 4. Crear venv:           python3 -m venv .venv && source .venv/bin/activate
[ ] 5. Instalar:             pip install -e ".[dev]"
[ ] 6. Verificar weasyprint: python3 -c "import weasyprint; print('OK')"
[ ] 7. Verificar matplotlib: python3 -c "import matplotlib; print('OK')"
[ ] 8. Crear .env producción con credenciales reales (NO sandbox)
[ ] 9. Verificar .env:       cat .env | grep FACTURAMA_API_URL
                              # Debe decir: https://api.facturama.mx/ (sin "sandbox")
[ ]10. Generar SECRET_KEY:   python3 -c "import secrets; print(secrets.token_hex(32))"
                              # Reemplazar el valor en .env
[ ]11. FLASK_ENV=production en .env
[ ]12. Borrar BD sandbox:    rm facturama_portal.db  (si empieza limpio)
[ ]13. Ejecutar tests:       pytest tests/ -v --tb=short
                              # Deben pasar los 45. Si fallan, corregir antes de continuar.
[ ]14. Iniciar Gunicorn:     gunicorn src.app:app --bind 0.0.0.0:5000 --workers 4 --timeout 120 &
[ ]15. Health check:         curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/
                              # Debe ser 200
[ ]16. Cargar dashboard:     curl -s http://localhost:5000/ | grep -q Dashboard && echo "OK"
[ ]17. Verificar reportes:   curl -s "http://localhost:5000/reports/" | grep -q "Centro de reportes" && echo "OK"
[ ]18. Instalar systemd:     sudo cp (crear archivo .service) → systemctl enable → start → status
```

#### Notas específicas para agentes

- **No uses `flask run` en producción.** Usa `gunicorn` como se indica arriba.
- **WeasyPrint requiere las dependencias del sistema** (paso 3). Si `import weasyprint` falla, instálalas primero.
- **La BD se crea automáticamente** al iniciar la app. Si quieres empezar limpio, borra `facturama_portal.db` antes de arrancar.
- **Si los tests fallan después de cambiar a producción**, probablemente es porque la BD de producción no tiene datos. Los tests usan una BD en memoria — no deberían fallar por esto.
- **No expongas el puerto 5000 directamente a internet.** Usa Nginx como reverse proxy con HTTPS.
- **Después de migrar, verifica manualmente** que puedas: (a) ver el dashboard, (b) crear un emisor, (c) timbrar una factura de prueba, (d) generar un reporte PDF.
- **Si algo falla**, revisa los logs: `journalctl -u facturama-portal -f` (systemd) o los archivos de log configurados en Gunicorn.

---

## Despliegue en VPS (Hetzner)

Esta sección describe cómo poner el portal —y un agente Hermes como administrador— en un servidor virtual (VPS) para uso en producción real, accesible desde internet, disponible 24/7.

### ¿Qué es un VPS?

Un VPS (Virtual Private Server) es una computadora virtual que rentas en un datacenter. Para efectos prácticos es **idéntico a tener una laptop con Ubuntu prendida 24/7**, pero sin ocupar espacio, sin consumir tu electricidad y con internet ultrarrápido de datacenter. Eliges cuánta RAM, CPU y disco necesitas, y pagas una renta mensual fija.

### ¿Por qué Hetzner?

| Ventaja | Detalle |
|---|---|
| **Precio** | El más bajo del mercado: ~$6 USD/mes por 4 GB RAM |
| **Rendimiento** | CPUs AMD EPYC, discos NVMe SSD |
| **Datacenters** | Alemania, Finlandia, EE.UU., Singapur |
| **Tráfico** | 20 TB incluidos (más que suficiente) |
| **Simplicidad** | Panel web limpio, despliegue en 30 segundos |

Hetzner es ideal para este proyecto: no necesitas balanceadores de carga, bases de datos administradas ni Kubernetes. Un solo VPS corre el portal + el agente sin problemas.

### Arquitectura: portal + agente en el mismo VPS

```
┌──────────────────────────────────────────────────────────┐
│  VPS Hetzner CX22 (Ubuntu 24.04)                         │
│  4 GB RAM · 2 vCPU · 40 GB NVMe · IP pública             │
│                                                          │
│  ┌──────────────────────┐  ┌───────────────────────────┐ │
│  │  Portal Facturama     │  │  Agente Hermes            │ │
│  │  Gunicorn :5000       │  │  Conectado a Telegram     │ │
│  │  systemd (auto-start) │  │  Atiende a Iván 24/7      │ │
│  └──────────────────────┘  └───────────────────────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Nginx :443 (HTTPS)                              │    │
│  │  facturama.socium.mx → :5000                     │    │
│  │  Certbot (Let's Encrypt, renovación automática)  │    │
│  └──────────────────────────────────────────────────┘    │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Base de datos SQLite (archivo .db local)         │    │
│  └──────────────────────────────────────────────────┘    │
└───────────────────────┬──────────────────────────────────┘
                        │ internet
          ┌─────────────┼─────────────┐
          │             │             │
     ┌────┴────┐  ┌────┴────┐  ┌─────┴──────┐
     │  Iván   │  │ Clientes│  │ Agente AI  │
     │(Telegram│  │(navega- │  │(administra │
     │ y nave- │  │ dor web)│  │ el VPS)    │
     │ gador)  │  │         │  │            │
     └─────────┘  └─────────┘  └────────────┘
```

El portal y el agente **no se estorban** — son procesos independientes. El portal escucha en el puerto 5000 y el agente se comunica por Telegram. Es como tener WhatsApp y Chrome abiertos en la misma computadora.

### Costos mensuales estimados

| Concepto | Proveedor | Costo USD | Costo MXN |
|---|---|---|---|
| VPS CX22 (4 GB RAM, 40 GB disco) | Hetzner | $6.00 | ~$120 |
| Dominio `.com` / `.mx` | Cloudflare / Namecheap | $1.00 | ~$20 |
| API Facturama (producción) | Facturama | Lo que ya pagas | — |
| **Total mensual** | | **~$7 USD** | **~$140 MXN** |

Si quieres aún más económico, el plan CX11 (2 GB RAM, 20 GB disco) cuesta ~$3.50 USD/mes (~$70 MXN) y también funciona para volúmenes bajos/medios.

### Paso a paso

#### 1. Crear el VPS en Hetzner

1. Ir a [hetzner.com/cloud](https://www.hetzner.com/cloud)
2. Crear cuenta y agregar método de pago
3. **Create Server:**
   - **Location:** Nuremberg (mejor latencia desde México) o Ashburn (EE.UU.)
   - **Image:** Ubuntu 24.04 LTS
   - **Type:** CX22 (4 GB RAM, 2 vCPU, 40 GB NVMe)
   - **SSH key:** Subir tu llave pública (`~/.ssh/id_rsa.pub`)
   - **Name:** `facturama`
4. Click **Create & Buy Now**

En 30 segundos tienes una IP pública, ej. `168.119.45.XXX`.

#### 2. Conectarse por SSH

```bash
ssh root@168.119.45.XXX
```

#### 3. Instalar dependencias del sistema

```bash
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git curl nginx certbot python3-certbot-nginx
apt install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev libcairo2
```

#### 4. Crear usuario de servicio (buena práctica de seguridad)

```bash
adduser --disabled-password --gecos "" facturama
usermod -aG sudo facturama
su - facturama
```

#### 5. Clonar e instalar el portal

```bash
cd /opt
sudo git clone https://github.com/IvanJS17/facturama-portal.git
sudo chown -R facturama:facturama facturama-portal
cd facturama-portal
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

#### 6. Crear archivo wsgi.py (entry point para Gunicorn)

El proyecto usa factory pattern (`create_app()`). Gunicorn necesita un objeto `app` a nivel módulo:

```bash
cat > /opt/facturama-portal/wsgi.py << 'EOF'
from src.app import create_app
app = create_app()
EOF
```

#### 7. Crear `.env` de producción

```bash
nano .env
```

```env
# Facturama API (PRODUCCIÓN — la URL NO lleva "sandbox")
FACTURAMA_USER=tu_usuario_produccion
FACTURAMA_PASSWORD=tu_password_produccion
FACTURAMA_API_URL=https://api.facturama.mx/

# Flask
FLASK_APP=src.app
FLASK_ENV=production
SECRET_KEY=<pega-el-valor-generado-con-secrets.token_hex(32)>

# Database
DATABASE_URL=sqlite:///facturama_portal.db
```

Generar SECRET_KEY:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Ajustar permisos del `.env`:

```bash
chmod 600 .env
```

#### 8. Verificar instalación

```bash
pytest tests/ -v --tb=short
# Deben pasar 45 tests

# Probar que la app carga
source .venv/bin/activate
gunicorn wsgi:app --bind 0.0.0.0:5000 --daemon
sleep 2
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/
# Debe devolver 200
pkill gunicorn
```

#### 9. Configurar systemd para el portal

```bash
sudo nano /etc/systemd/system/facturama-portal.service
```

```ini
[Unit]
Description=Facturama Portal
After=network.target

[Service]
User=facturama
WorkingDirectory=/opt/facturama-portal
EnvironmentFile=/opt/facturama-portal/.env
ExecStart=/opt/facturama-portal/.venv/bin/gunicorn wsgi:app --bind 127.0.0.1:5000 --workers 4 --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> **Nota:** En VPS con Nginx como proxy, Gunicorn solo escucha en `127.0.0.1:5000` (localhost), NO en `0.0.0.0`. Nginx es el que recibe tráfico externo en el puerto 443 y lo reenvía.

```bash
sudo systemctl daemon-reload
sudo systemctl enable facturama-portal
sudo systemctl start facturama-portal
sudo systemctl status facturama-portal
```

#### 10. Configurar dominio y HTTPS

Si tienes un dominio (ej. `facturama.socium.mx`), apunta un registro A a la IP del VPS. Luego:

```bash
sudo nano /etc/nginx/sites-available/facturama
```

```nginx
server {
    listen 80;
    server_name facturama.socium.mx;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name facturama.socium.mx;

    ssl_certificate     /etc/letsencrypt/live/facturama.socium.mx/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/facturama.socium.mx/privkey.pem;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

Activar el sitio y obtener certificado SSL:

```bash
sudo ln -s /etc/nginx/sites-available/facturama /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # Quitar el default
sudo nginx -t  # Verificar sintaxis
sudo systemctl reload nginx
sudo certbot --nginx -d facturama.socium.mx
```

Certbot configura la renovación automática (cada 90 días). Verificar:

```bash
sudo certbot renew --dry-run
```

#### 11. Firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

#### 12. Instalar el agente Hermes en el VPS

```bash
# Como usuario facturama (no root)
curl -fsSL https://hermes.nousresearch.com/install.sh | bash
hermes setup
hermes config set provider <tu-provider>
hermes config set model <tu-modelo>
hermes connect telegram
```

El agente vive como proceso en background y recibe tus mensajes por Telegram. Desde ahí puede administrar el portal: monitorear, reiniciar, depurar, agregar features.

#### 13. Verificación final

```bash
# Portal responde
curl -s -o /dev/null -w "%{http_code}" https://facturama.socium.mx
# 200

# Dashboard carga
curl -s https://facturama.socium.mx | grep -q Dashboard && echo "OK"

# Reportes funcionan
curl -s "https://facturama.socium.mx/reports/" | grep -q "Centro de reportes" && echo "OK"

# Servicio systemd OK
sudo systemctl status facturama-portal | grep -q "active (running)" && echo "OK"

# Nginx OK
sudo nginx -t && echo "OK"

# SSL activo
curl -sI https://facturama.socium.mx | grep -q "HTTP/2 200" && echo "OK"
```

---

### Checklist de despliegue para agentes AI

Si eres un agente AI encargado de desplegar este proyecto en un VPS Hetzner nuevo:

```
[ ] 1. Verificar acceso SSH al VPS:      ssh root@<IP>
[ ] 2. apt update && apt upgrade -y
[ ] 3. Instalar paquetes:                apt install python3 python3-pip python3-venv git curl nginx certbot python3-certbot-nginx -y
[ ] 4. Dependencias WeasyPrint:          apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev libcairo2 -y
[ ] 5. Crear usuario facturama:          adduser facturama && usermod -aG sudo facturama
[ ] 6. Clonar repo en /opt:              git clone https://github.com/IvanJS17/facturama-portal.git /opt/facturama-portal
[ ] 7. chown -R facturama:facturama /opt/facturama-portal
[ ] 8. Crear venv:                       python3 -m venv .venv && source .venv/bin/activate
[ ] 9. Instalar:                         pip install -e ".[dev]"
[ ]10. Crear wsgi.py:                     echo 'from src.app import create_app\napp = create_app()' > wsgi.py
[ ]11. Crear .env con credenciales de PRODUCCIÓN (NO sandbox)
[ ]12. chmod 600 .env
[ ]13. pytest tests/ -v --tb=short       # 45 tests deben pasar
[ ]14. Crear /etc/systemd/system/facturama-portal.service (usar wsgi:app)
[ ]15. systemctl enable facturama-portal && systemctl start facturama-portal
[ ]16. curl localhost:5000 → 200
[ ]17. Configurar Nginx + Certbot para HTTPS
[ ]18. Configurar ufw: solo 22, 80, 443
[ ]19. Instalar Hermes: bash <(curl -fsSL https://hermes.nousresearch.com/install.sh)
[ ]20. hermes setup && hermes connect telegram
[ ]21. Verificar dominio con HTTPS:      curl https://<dominio> → 200
[ ]22. Probar flujo completo: navegar dashboard, crear emisor, timbrar factura, generar PDF
```

### Seguridad en el VPS

| Medida | Comando / Acción |
|---|---|
| SSH solo con llave (sin contraseña) | `sudo nano /etc/ssh/sshd_config` → `PasswordAuthentication no` |
| `.env` con permisos restrictivos | `chmod 600 /opt/facturama-portal/.env` |
| Firewall mínimo | Solo puertos 22, 80, 443 abiertos |
| HTTPS obligatorio | Nginx redirige HTTP → HTTPS |
| Actualizaciones automáticas de seguridad | `sudo apt install unattended-upgrades && sudo dpkg-reconfigure unattended-upgrades` |
| No ejecutar como root | El servicio corre como usuario `facturama` |
| Backups de la BD | Cron job: `cp facturama_portal.db backups/$(date +%Y%m%d).db` |

---

## Licencia

Privado — uso interno.
