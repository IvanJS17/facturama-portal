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

## Licencia

Privado — uso interno.
