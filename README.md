# BallChaser

API multiusuario que sincroniza los replays de Rocket League de cada usuario desde
[Ballchasing](https://ballchasing.com), guarda las metricas relevantes en su propia base de
datos y calcula tendencias de progreso. Frontend en React con las graficas.

La especificacion completa esta en [`Guia.md`](Guia.md). Este README describe el estado real
del repositorio.

## Estado

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Esqueleto: `pyproject`, ruff, pre-commit, FastAPI con `/health`, Dockerfile, docker-compose, CI | Hecho |
| 1 | Firebase Auth, `users`, `GET /me`, `DELETE /me` | Hecho (falta el proyecto de Firebase en la nube) |
| 2 | Cifrado del token de Ballchasing y `game_accounts` | Pendiente |
| 3 | Cliente Ballchasing, ingesta, cola `sync_jobs` y worker | Pendiente |
| 4 | API de estadisticas y tendencias | Pendiente |
| 5 | Frontend React + Vite | Pendiente |
| 6 | Observabilidad, Prometheus, README final, ADR | Pendiente |

## Estructura

```
backend/
  app/
    api/routes/  # health, users (/me)
    core/         # configuracion, seguridad (Firebase), errores, logging
    db/           # modelos, sesion
    services/     # logica de usuario
  migrations/     # Alembic
  tests/
  Dockerfile
  pyproject.toml
docs/
  adr/
docker-compose.yml
.github/workflows/
```

## Requisitos previos

- Python 3.12 o superior.
- Docker Desktop (opcional: solo hace falta para levantar Postgres en local). Docker
  Desktop necesita WSL2; en Windows se instala con `wsl --install` desde una terminal de
  **administrador** y despues hay que reiniciar el equipo.
- Un proyecto de Firebase (solo para probar el login de verdad; los tests no lo necesitan).

## Puesta en marcha

### 1. Dependencias de Python

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

### 2. Base de datos

Con Docker:

```bash
docker compose up -d db
cd backend && alembic upgrade head
```

O con una URL propia en `DATABASE_URL` (Neon en produccion):

```bash
cd backend && alembic upgrade head
```

### 3. API

```bash
docker compose up --build
```

La API queda en <http://localhost:8000>; la documentacion interactiva, en
<http://localhost:8000/docs> (solo fuera de produccion). Sin Docker, tambien vale:

```bash
cd backend && uvicorn app.main:app --reload
```

Comprobar que todo va bien:

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0"}
```

### 4. Firebase

1. Crear el proyecto en <https://console.firebase.google.com> (plan **Spark**, sin
   facturacion) llamado `ballchaser`.
2. En *Authentication → Sign-in method*, activar **Email/Password** y **Google**.
3. En *Project settings → Service accounts*, pulsar **Generate new private key**. Se descarga
   un JSON.
4. Mover ese JSON a `backend/secrets/firebase-service-account.json` (la carpeta `secrets/`
   esta en `.gitignore`) y anadir a `backend/.env`:
   ```
   FIREBASE_CREDENTIALS_FILE=secrets/firebase-service-account.json
   ```
   En Render, la variable de entorno `FIREBASE_CREDENTIALS_JSON` con el JSON entero, en una
   sola linea.
5. Comprobar: `curl -H "Authorization: Bearer cualquier-cosa" http://localhost:8000/me`
   debe devolver **401** (credenciales cargadas, token falso) y no 503.
6. El frontend (fase 5) hara `signInWithEmailAndPassword` o `signInWithPopup` y enviara
   `getIdToken()` en la cabecera `Authorization: Bearer`.

Sin esas credenciales, las rutas `/me` devuelven 503 `auth_not_configured` y las demas siguen
funcionando: es deliberado, fallar cerrado.

**Ese JSON es una llave que da acceso a todos los usuarios del proyecto.** Si se filtra,
borralo en *Project settings → Service accounts* y genera otra. Nunca lo subas a Git.

## Migraciones

```bash
alembic revision --autogenerate -m "mensaje"   # crea la migracion desde los modelos
alembic upgrade head                           # aplica
alembic downgrade -1                           # deshace el ultimo paso
alembic upgrade head --sql                      # genera el SQL sin conectar (lo usa CI)
```

## Calidad

```bash
ruff check . && ruff format --check .   # lint y formato
mypy                                   # tipos
pytest                                 # tests
pre-commit install                     # hooks en el commit
```

Notas sobre los tests:

- Usan **SQLite en memoria**, asi que no necesitan Docker. Para correrlos contra Postgres:
  `docker compose exec db psql -U ballchaser -d postgres -c "CREATE DATABASE ballchaser_test"` y
  despues `TEST_DATABASE_URL=postgresql+psycopg://ballchaser:ballchaser@localhost:5432/ballchaser_test pytest`.
- Firebase se sustituye por un verificador falso: los tests de auth comprueban que un token
  invalido no pasa, sin tocar la red.
- Entre tests se limpia la base de datos (`TRUNCATE` en Postgres). Sin eso cada test ve las
  filas del anterior y los resultados dependen del orden de ejecucion.
- En Windows, psycopg necesita el event loop `Selector` y no el `Proactor` de por defecto.
  El proyecto lo fuerza en `app/core/asyncio_setup.py`, para que `alembic` y `uvicorn` se
  comporten igual que en Linux.

## CI

`.github/workflows/ci.yml` define tres jobs:

| Job | Que comprueba |
|---|---|
| `backend` | ruff, mypy, tests con cobertura, `pip-audit` y el SQL de las migraciones |
| `backend-postgres` | los mismos tests contra un Postgres real, mas el ciclo `upgrade / downgrade / upgrade` de Alembic |
| `docker` | construye la imagen del backend |

## Hosting previsto

| Pieza | Servicio |
|---|---|
| API | Render (Docker) |
| Base de datos | Neon (Postgres) |
| Identidad | Firebase Auth (plan Spark) |
| Frontend | GitHub Pages |
| CI y cron | GitHub Actions |

Nota: el servicio gratuito de Render se duerme tras 15 minutos sin trafico; por eso el
sincronizado se lanzara desde un workflow programado que llama a `/internal/cron/sync`.