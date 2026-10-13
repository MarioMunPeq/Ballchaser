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
| 1 | Firebase Auth, `users`, `GET /me`, `DELETE /me` | Pendiente |
| 2 | Cifrado del token de Ballchasing y `game_accounts` | Pendiente |
| 3 | Cliente Ballchasing, ingesta, cola `sync_jobs` y worker | Pendiente |
| 4 | API de estadisticas y tendencias | Pendiente |
| 5 | Frontend React + Vite | Pendiente |
| 6 | Observabilidad, Prometheus, README final, ADR | Pendiente |

## Estructura

```
backend/
  app/
    api/         # routers
    core/        # configuracion y logging
  tests/
  Dockerfile
  pyproject.toml
docs/
  adr/
docker-compose.yml
.github/workflows/
```

## Desarrollo local

Requisitos: Python 3.12+ y Docker.

```bash
git clone <repo> && cd ballchaser
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
cp .env.example .env
```

Levantar la API y Postgres:

```bash
docker compose up --build
```

La API queda en <http://localhost:8000>; la documentacion interactiva, en
<http://localhost:8000/docs> (solo fuera de produccion).

Comprobar que todo va bien:

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0"}
```

## Calidad

```bash
ruff check . && ruff format --check .   # lint y formato
mypy                                   # tipos
pytest                                 # tests
pre-commit install                     # hooks en el commit
```

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