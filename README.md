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
| 1 | Firebase Auth, `users`, `GET /me`, `DELETE /me` | Hecho |
| 2 | Cifrado del token de Ballchasing y `game_accounts` | Hecho |
| 3 | Cliente Ballchasing, ingesta, cola `sync_jobs` y worker | Hecho (falta el cron de GitHub Actions) |
| 4 | API de estadisticas y tendencias | Hecho |
| 5 | Frontend React + Vite | Hecho (falta la config web de Firebase y el despliegue) |
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
frontend/            # React + Vite + TS, tema oscuro, movil primero
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

## Cómo funciona Ballchasing

Ballchasing es una web donde se suben partidas de Rocket League y calcula sus
estadísticas: boost, posicionamiento, demos, disparos, cámara...

- Rocket League guarda cada partida como un fichero `.replay`. En Steam están en
  `C:\Users\<tu-usuario>\Documents\My Games\Rocket League\Replays`.
- Se pueden subir arrastrándolos a <https://ballchasing.com> (pestaña *Upload*). Esta
  aplicación **no** los sube.
- Quien sube la partida es el *uploader*. Los jugadores de dentro se identifican por su
  id de plataforma (`steam:76561199085282414`), no por su nombre.

Lo importante para el diseño: **no hace falta que subas tus partidas.** El listado acepta
filtrar por `player-id` y devuelve las partidas en las que jugaste, se las haya subido
quien se las haya subido (comprobado: un jugador con 1578 replays de subiadores
distintos). Por eso la ingesta usará las cuentas de juego (`game_accounts`) y no
`uploader=me`.

Detalle verificado en [`docs/ballchasing-api.md`](docs/ballchasing-api.md).

Tu SteamID64 esta en la URL de tu perfil de Steam:
`https://steamcommunity.com/profiles/76561199085282414/`.

## Credenciales de Ballchasing

Cada usuario guarda su propio token, cifrado con AES-GCM. La clave es una variable de
entorno; generarla con:

```bash
cd backend
python -c "from app.core.crypto import generar_clave; print(generar_clave())"
```

y escribirla en `.env` como `SECRET_ENCRYPTION_KEY=...`.

| Endpoint | Que hace |
|---|---|
| `PUT /me/ballchasing-token` | Valida el token contra Ballchasing y lo guarda cifrado |
| `GET /me/ballchasing-token` | Estado (configurado, validado, fecha). **Nunca el token** |
| `DELETE /me/ballchasing-token` | Lo borra |
| `GET /me/game-accounts` | Cuentas de juego del usuario |
| `POST /me/game-accounts` | Anade una (platform, platform_id, display_name) |
| `DELETE /me/game-accounts/{id}` | Borra una propia |

Distincion de errores importante: un **401** significa que Ballchasing no reconoce el
token (error del usuario) y un **502** que Ballchasing no esta disponible (no es culpa
del token, asi que no se le pide que lo cambie).

Si se rota la clave, `key_version` guarda con que clave se cifro cada fila para poder
descifrar las antiguas: se cambia `SECRET_ENCRYPTION_KEY` y se sube `SECRET_KEY_VERSION`,
y las filas viejas siguen siendo legibles con la clave que les tocó.

## Sincronizacion

`POST /sync` no sincroniza: encola un trabajo en la tabla `sync_jobs` y responde
`202`. El worker, que vive en el mismo proceso, lo coge y lo ejecuta.

```
POST /sync                encola (si ya hay uno pendiente, no encola otro)
GET  /sync/status         estado del ultimo trabajo y progreso
PATCH /me/sync-settings   activa o desactiva la sincronizacion automatica
```

Decisiones que importan al leer el codigo:

- **Idempotente**: `replays.ballchasing_id` es la clave primaria y una partida ya
  guardada se descarta *antes* de pedir su detalle. El worker puede morir y repetirse
  sin duplicar nada ni gastar cuota.
- **Una partida por transacción** (con *savepoint*): una partida imposible no tira el lote.
- **`status` distinto de `ok`** no se guarda: ni se marca como vista, para que la
  siguiente pasada vuelva a mirarla.
- **Un 429 no es un fallo**: el trabajo vuelve a la cola con espera creciente. Es cuota
  de Ballchasing, no un error del usuario.
- **Recorrido acotado**: para tras dos páginas seguidas sin nada nuevo. El listado viene
  de más reciente a más antiguo, así que seguir más allá solo es gastar cuota.
- **Trabajos a medias se recuperan**: si el proceso muere, un barrido devuelve a la cola
  los que llevan más de 30 minutos en `running`.

`DELETE /me` borra también las estadísticas del jugador y las partidas que se quedan sin
referencia: son datos personales de una cuenta que ya no existe.

## API de datos

Todas exigen token de Firebase y siempre devuelven lo del usuario del token.

```
GET /replays?playlist=&result=&desde=&hasta=&limit=&offset=
GET /replays/{id}
GET /stats/summary?playlist=&desde=&hasta=
GET /stats/trends?metric=bpm&interval=week&playlist=&desde=&hasta=
```

Decisiones que conviene conocer:

- **`metric` e `interval` son listas cerradas.** El nombre de la columna llega del
  cliente, así que se resuelve con un diccionario; aceptarlo tal cual sería una
  inyección de SQL esperando a ocurrir. Un valor desconocido da 422.
- **Los periodos sin datos se omiten**, no se rellenan con ceros: un 0 donde no se jugó
  hace que la gráfica parezca una caída de rendimiento.
- **`hasta=2026-05-01` incluye ese día entero**, no solo las 00:00.
- **`win_rate` no cuenta los empates** como derrotas: se calcula sobre las partidas con
  resultado claro.
- **`GET /replays/{id}` devuelve solo tus estadísticas**, porque solo se guardan las
  tuyas (ADR 0004).

Rendimiento medido con 3000 partidas: el listado filtrado usa los índices y tarda menos
de 1 ms; el resumen y las tendencias, ~1 y ~5 ms. Detalle en
[`docs/rendimiento.md`](docs/rendimiento.md).

## Frontend

React + Vite + TypeScript, tema oscuro, pensado para móvil primero.

```bash
cd frontend
npm install
cp .env.example .env.local   # y rellena las 4 variables de Firebase
npm run dev                  # http://localhost:5173
```

Las cuatro variables de Firebase salen de *Project settings → Your apps → Web app*.
Son **valores publicos** (identifican el proyecto, no dan acceso): lo que protege de
verdad es que la API verifique el ID token en el servidor.

La API tiene que permitir el origen del frontend en CORS. En local ya esta
(`http://localhost:5173`). Al desplegar en GitHub Pages habra que anadir
`https://<usuario>.github.io` a `CORS_ORIGINS` en Render.

### Decisiones del frontend

- **D3 solo para lo matematico** (escalas, ejes, forma de la linea) y React para el
  DOM. Se evita `d3.select()` sobre el SVG porque React ya gestiona el DOM.
- **Numeros y fechas formateados a mano**, sin `toLocaleString`. Su resultado depende de
  los datos de idioma del runtime: en un Node con ICU reducido devuelve `1234` en vez de
  `1.234`, y la misma pantalla se veria distinta segun donde corra.
- **Los periodos sin datos no se pintan.** La serie se filtra antes de escalar, para que
  un 0 donde no jugaste no parezca una caida de rendimiento.
- **Tests solo de logica pura** (formateo, series, escala del eje): es donde se rompen
  las cosas y no depende del DOM. Los componentes los cubre el navegador.

| Comando | Que hace |
|---|---|
| `npm run dev` | Servidor de desarrollo |
| `npm run build` | Compila a `dist/` (comprueba tipos antes) |
| `npm run typecheck` | Solo `tsc --noEmit`, en modo estricto |
| `npm run lint` | ESLint |
| `npm test` | Vitest |

Despliegue: `.github/workflows/deploy-frontend.yml` publica en GitHub Pages en cada push
a `main`. Hay que activar **Settings → Pages → Source: GitHub Actions**. El workflow
copia `index.html` a `404.html` porque Pages no reescribe rutas y, sin eso, recargar en
`/ajustes` daria un 404.

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

## Documentacion

| Documento | Que contiene |
|---|---|
| [`Guia.md`](Guia.md) | Especificacion original, fases y decisiones abiertas |
| [`docs/ballchasing-api.md`](docs/ballchasing-api.md) | La API de Ballchasing verificada con peticiones reales: filtros, paginacion y forma exacta de las estadisticas |
| [`docs/rendimiento.md`](docs/rendimiento.md) | Planes de ejecucion y tamaño en disco con 3000 partidas |
| [`docs/adr/`](docs/adr/) | Decisiones tecnicas con su contexto y sus consecuencias |

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