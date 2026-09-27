# Contador de Inventario Totto — API

FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL. Gestionado con **uv**.

## Puesta en marcha

```bash
cp .env.example .env            # y completa DATABASE_URL
uv sync
uv run alembic upgrade head     # crea/actualiza el esquema
uv run fastapi dev app/main.py  # http://localhost:8000/docs
```

Cargar Excel desde la terminal (el tipo se detecta solo):

```bash
uv run python -m app.cli import ../BarrcodeFQ95.xlsx "../data - 2026-09-26T101702.972.xlsx"
```

Pruebas y calidad: `uv run pytest` (las de API usan SQLite en memoria, no tocan la base) · `uv run ruff check .` · `uv run ruff format .`

## Usuarios y roles

Login con usuario y contraseña (Argon2id). La sesión es un JWT en una **cookie httpOnly**
(12 h, configurable) y toda escritura exige la cabecera `X-Requested-With: fetch` (CSRF).
5 intentos fallidos bloquean el usuario 5 minutos.

| Acción | Asesor | Administrador |
|---|:-:|:-:|
| Contar (escanear, ±1, registrar/asociar códigos) | ✔ | ✔ |
| Deshacer lecturas | solo las suyas | todas |
| Ver conteos y diferencias, buscar en catálogo | ✔ | ✔ |
| Crear, renombrar, cerrar, reabrir y eliminar conteos | | ✔ |
| Elegir existencias de comparación, exportar Excel | | ✔ |
| Subir Excel, eliminar reportes | | ✔ |
| Gestionar usuarios (crear, rol, tienda, restablecer, desactivar) | | ✔ |

Un usuario con **tienda asignada** solo ve y opera esa tienda (un administrador de tienda
solo gestiona usuarios de su tienda). Sin tienda = todas. Los usuarios nuevos o
restablecidos reciben una **contraseña temporal** que deben cambiar al ingresar; cambiarla,
restablecerla o desactivar al usuario cierra sus demás sesiones. Siempre debe quedar al
menos un administrador activo.

Crear el primer administrador (o cualquier usuario) desde la terminal:

```bash
uv run python -m app.cli create-user admin --name "Nombre Apellido" --role administrador
uv run python -m app.cli create-user catalina.perez --name "Catalina Pérez" --store FQ95
```

Variables nuevas en `.env`: `SECRET_KEY` (≥ 32 caracteres, obligatoria) y
`COOKIE_SECURE=true` en producción con HTTPS. Si el frontend y el API quedan en dominios
distintos, sírvelos bajo el mismo sitio (p. ej. `app.midominio.com` y `api.midominio.com`)
para que la cookie funcione en Safari/iOS.

## Modelo de negocio

| Tabla | Qué representa |
|---|---|
| `stores` | Punto de venta (`FQ95 - TOTTO VILLA GORGONA`). Se crea al importar existencias. |
| `products` | Catálogo unificado. `reference` = *Código Producto Largo*; `ean` = código de barras de la etiqueta (lo que se escanea). |
| `stock_snapshots` / `_lines` | Cada carga del reporte de existencias ("lo que debería haber"). Es versionado porque el reporte cambia ~2 veces al día. |
| `count_sessions` | Una jornada de conteo en una tienda. Se compara contra un snapshot fijo o, por defecto, contra el más reciente. |
| `count_entries` | Eventos de conteo (append-only, con cantidad ±). Permiten varios celulares a la vez, deshacer y auditoría (usuario, zona, hora). |
| `users` | Personas con acceso: rol (`asesor` / `administrador`), tienda asignada opcional. |

**Convención de columnas del maestro de códigos:** `BARCODE` = EAN-13 impreso en la
etiqueta (lo que se escanea); `Código Producto Largo` o `SKU` = referencia Totto.
El `BarrcodeFQ95.xlsx` original trae esos dos encabezados invertidos: el importador lo
detecta por el contenido, lo corrige y avisa (`columnsSwapped: true`) para que se
renombren las columnas en el archivo.

Estados de la comparación: `ok` (cuadrado), `missing` (faltante), `surplus` (sobrante),
`unexpected` (contado pero no está en existencias). Las referencias esperadas sin EAN
se reportan aparte (`linesWithoutEan`): no se pueden escanear hasta asociarles un código,
cosa que la app permite hacer al escanear una etiqueta desconocida.

## Endpoints principales (`/api/v1`)

- `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/change-password`
- `GET|POST /users`, `PATCH /users/{id}`, `POST /users/{id}/reset-password` (admin)

- `POST /imports` — sube un `.xlsx` (existencias o maestro de códigos; `kind` y `effectiveAt` opcionales).
- `GET /stores`, `GET /stores/{id}/snapshots`, `GET /stores/{id}/sessions`
- `POST /sessions`, `GET|PATCH|DELETE /sessions/{id}`
- `POST /sessions/{id}/scans` — `{code | productId, quantity, countedBy, zone}`; 404 `product_not_found` si el código no existe.
- `GET /sessions/{id}/scans`, `DELETE /sessions/{id}/scans/{entryId}` (deshacer)
- `GET /sessions/{id}/comparison?snapshotId=`, `GET /sessions/{id}/export` (Excel)
- `GET /products?q=`, `GET /products/lookup/{code}`, `POST /products` (registrar/asociar EAN)
