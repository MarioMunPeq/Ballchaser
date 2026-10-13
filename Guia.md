# BallChaser — Analizador de replays de Rocket League

> Nombre provisional. Documento de definición v1 (octubre 2026).
> Los límites de planes gratuitos cambian: comprobarlos antes de empezar cada fase.

## 1. Resumen

API multiusuario que sincroniza los replays de cada usuario desde Ballchasing, guarda las métricas relevantes en una base de datos propia y calcula tendencias de progreso (por semana, playlist, temporada). Un frontend en React muestra las gráficas.

**Objetivo de portfolio:** demostrar backend real: auth delegada, secretos cifrados, cola de trabajos, rate limiting contra una API externa, modelado de datos, tests, CI, Docker y observabilidad, todo con coste 0 €.

## 2. Alcance

### Dentro de v1

- Registro e inicio de sesión con email/contraseña y con Google (Firebase Authentication).
- Cada usuario guarda su propio token de Ballchasing (cifrado).
- Sincronización de replays en segundo plano, manual y programada.
- Estadísticas: resumen, tendencias y listado de partidas con filtros.
- Frontend con panel de progreso.
- Tests, CI, Docker, logs estructurados y métricas.

### Fuera de v1

- Ligas, torneos y equipos.
- Bot de Discord.
- Subida de replays desde la app (el usuario sube sus replays a Ballchasing como ya haga hoy).
- Comparativas entre usuarios.

## 3. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Enfoque | Analizador de progreso personal |
| Usuarios | Varios, cada uno con su cuenta |
| Login | Email/contraseña y Google, vía Firebase Authentication |
| Backend | FastAPI (Python) |
| Base de datos | PostgreSQL en Neon |
| Frontend | React + Vite + TypeScript |
| Ingeniería | Tests, CI, ADR, Docker, logs estructurados y métricas |
| Coste | 0 € |

## 4. Arquitectura

```
React (GitHub Pages)
   │  login con Firebase JS SDK → ID token (JWT)
   ▼
FastAPI (Render, Docker) ──► Neon Postgres
   │        ▲
   │        └── GitHub Actions (cron) → POST /internal/cron/sync
   ▼
Ballchasing API (token de cada usuario)
```

Componentes dentro del backend:

- **API HTTP:** routers, validación con Pydantic, autorización por usuario.
- **Worker:** tarea asíncrona en el propio proceso que consume `sync_jobs`.
- **Cliente Ballchasing:** `httpx` con rate limiter por token y reintentos.
- **Capa de datos:** SQLAlchemy 2 + Alembic.

## 5. Autenticación (Firebase en pocas líneas)

Firebase se encarga de la identidad; tu backend se encarga de los permisos.

1. En el frontend, el SDK de Firebase hace el login (email/contraseña o Google) y devuelve un **ID token** (un JWT firmado por Google).
2. El frontend envía ese token en cada petición: `Authorization: Bearer <token>`.
3. FastAPI **verifica la firma** del token (con `firebase-admin` o validando contra las claves públicas de Google) y obtiene el `uid`.
4. Si es la primera vez que ese `uid` llega, se crea la fila en `users`.

Ventajas: no guardas contraseñas, no implementas recuperación de cuenta ni verificación de email, y Google login viene incluido.
Contrapartida: no practicas hashing de contraseñas; lo compensas con autorización, cifrado de secretos y tests de seguridad.

Plan gratuito (Spark): email/contraseña y Google están incluidos sin coste. Según la documentación oficial de límites, sin método de facturación hay un máximo de 3000 usuarios activos al día y 150 emails de restablecimiento de contraseña al día. Para este proyecto sobra.

Nota: tu Dungeon Archive ya usa Firebase Auth, así que parte de la configuración te sonará.

## 6. Integración con Ballchasing

- Autenticación: cabecera `Authorization: <token>` con el token del usuario.
- Listado de replays: `GET /replays`, con filtros como `uploader=me`, `playlist`, `season`, `replay-date-after`, `count` (máx. 200) y paginación con el enlace `next`.
- Detalle y estadísticas: `GET /replays/{id}`.
- Cuando se supera el límite, devuelve `429`: hay que esperar y reintentar.

**Límites del plan sin patrocinio (tier "all others"):**

| Endpoint | Límite |
|---|---|
| Listar replays | 2 llamadas/s, 500/hora |
| Detalle de replay | 2 llamadas/s, 1000/hora |
| Descargar archivo del replay | 1 llamada/s, 200/hora |

Consecuencias de diseño:

- La v1 **no descarga archivos**; solo usa listado y detalle.
- Cada usuario aporta su token, así que la cuota es **por usuario**, no global.
- Replays ya sincronizados no se vuelven a pedir.

Detalles a tener en cuenta:

- Algunos contadores (`epic_saves`, `clears`, `centers`, `aerial_hits`, `first_touches`, `flip_resets`, etc.) solo existen en replays posteriores a la actualización de septiembre de 2026. Las demos por mitad de campo solo están en replays procesados desde octubre de 2026. Esas columnas son **nullable**.
- La documentación marca `player-name` y `player-id` como obligatorios en el listado, pero también ofrece `uploader=me`. **Verificar con una petición real** qué combinación de filtros acepta antes de fijar el diseño.
- Un replay puede estar en estado `pending` o `failed`: no guardar estadísticas hasta que sea `ok`.

## 7. Modelo de datos

```
users
  id (uuid, pk), firebase_uid (unique), email, display_name, created_at

ballchasing_credentials
  user_id (pk, fk users), token_encrypted, key_version, last_validated_at, created_at

game_accounts
  id, user_id (fk), platform, platform_id, display_name
  unique (user_id, platform, platform_id)

replays
  ballchasing_id (pk), played_at, playlist_id, map_code, team_size,
  duration, play_duration, overtime, season, season_type,
  blue_goals, orange_goals

user_replays
  user_id (fk), replay_id (fk), game_account_id (fk), team, result (win/loss)
  unique (user_id, replay_id)

player_stats
  replay_id (fk), platform, platform_id, name, team,
  -- core
  score, goals, assists, saves, shots, shooting_percentage,
  -- boost
  bpm, avg_amount, percent_zero_boost, percent_full_boost, amount_stolen,
  -- movement
  avg_speed, percent_supersonic_speed, percent_ground, percent_low_air, percent_high_air,
  -- positioning
  percent_defensive_third, percent_offensive_third, percent_behind_ball,
  percent_most_back, percent_most_forward,
  -- demos
  demos_inflicted, demos_taken,
  -- nullable (replays recientes)
  epic_saves, clears, centers, aerial_hits, first_touches, flip_resets,
  demos_inflicted_def_half, demos_inflicted_off_half
  primary key (replay_id, platform, platform_id)

sync_jobs
  id, user_id (fk), type, status (queued/running/done/failed),
  attempts, run_after, last_error, created_at, started_at, finished_at

sync_state
  user_id (pk, fk), last_synced_at, last_replay_date, auto_sync (bool)
```

Reglas:

- Guardar **solo estas métricas**, no el JSON completo, para caber en el almacenamiento gratuito de Neon (entre 0,5 y 1 GB por proyecto según la fuente).
- `replays.ballchasing_id` como clave primaria hace la ingesta idempotente (`ON CONFLICT DO NOTHING`).
- Índices: `user_replays(user_id)`, `replays(played_at)`, `sync_jobs(status, run_after)`.

## 8. API

Todas las rutas (salvo `/health`) exigen token de Firebase.

**Usuario**

- `GET /me` — crea el usuario si es la primera vez y devuelve el perfil.
- `DELETE /me` — borra cuenta y datos.

**Credenciales y cuentas de juego**

- `PUT /me/ballchasing-token` — valida contra Ballchasing y guarda cifrado.
- `GET /me/ballchasing-token` — estado (configurado, validado), nunca el token.
- `DELETE /me/ballchasing-token`
- `GET|POST|DELETE /me/game-accounts`

**Sincronización**

- `POST /sync` — encola un trabajo (limitado para evitar abuso).
- `GET /sync/status` — último estado y próximo intento.
- `PATCH /me/sync-settings` — activar o desactivar sincronización automática.

**Datos**

- `GET /replays?playlist=&result=&from=&to=&page=` — listado paginado.
- `GET /replays/{id}` — detalle con estadísticas de los jugadores.
- `GET /stats/summary?playlist=&from=&to=` — victorias, goles, paradas, medias.
- `GET /stats/trends?metric=&interval=week&playlist=` — serie temporal de una métrica.

**Operación**

- `GET /health` — público.
- `GET /metrics` — Prometheus, protegido.
- `POST /internal/cron/sync` — llamado por GitHub Actions, protegido con secreto en cabecera.

## 9. Sincronización y cola de trabajos

1. `POST /sync` (o el cron) inserta un trabajo en `sync_jobs`.
2. El worker toma trabajos con `SELECT ... FOR UPDATE SKIP LOCKED`, sin necesidad de Redis.
3. Pide a Ballchasing los replays posteriores a `last_replay_date` y, para cada uno nuevo, su detalle.
4. Inserta `replays`, `user_replays` y `player_stats` en una transacción por replay.
5. Si recibe `429`: espera con *backoff* exponencial con *jitter* y reprograma el trabajo (`run_after`).
6. Si falla de forma persistente: `failed` con `last_error`, sin bloquear al resto.

**Rate limiter:** *token bucket* por token de usuario, ajustado a 2 req/s y a la cuota horaria. Vive en memoria (una sola instancia); si el servicio se reinicia, se reconstruye y se apoya en el manejo de `429`.

**Servicio gratuito que se duerme:** Render apaga el servicio tras 15 minutos sin tráfico y tarda alrededor de un minuto en despertar. Por eso:

- Un workflow programado de GitHub Actions llama a `/internal/cron/sync`, lo que despierta el servicio y procesa la cola.
- El worker puede ser interrumpido en cualquier momento: los trabajos deben ser reanudables e idempotentes.

## 10. Seguridad

- Token de Ballchasing cifrado con AES-GCM (o Fernet) usando `cryptography`; la clave en variable de entorno y `key_version` para poder rotarla.
- El token nunca se devuelve por la API ni aparece en logs.
- Autorización por propietario en todas las consultas (`user_id` del token, nunca del cuerpo de la petición).
- CORS restringido al dominio del frontend.
- Límite de peticiones por usuario en endpoints costosos (`/sync`).
- Secreto del cron comparado en tiempo constante.
- Dependencias revisadas en CI (`pip-audit`).

## 11. Observabilidad y calidad

- **Logs:** JSON estructurado con `structlog`, un `request_id` por petición y `user_id` cuando exista.
- **Métricas** (`prometheus-client`): peticiones por ruta y estado, duración, trabajos por estado, respuestas 429 de Ballchasing, replays ingeridos.
- **Visualización opcional:** Prometheus + Grafana en `docker compose` local. En la nube, un panel gratuito opcional (comprobar límites).
- **Tests:** `pytest` + `httpx.AsyncClient`; Postgres real en Docker; Ballchasing simulado con `respx`. Cubrir: auth, aislamiento entre usuarios, cifrado, ingesta idempotente, reintentos ante 429, agregaciones.
- **Calidad:** `ruff` (lint y formato), `mypy` en modo razonable, `pre-commit`.
- **CI (GitHub Actions):** lint, tipos, tests, construcción de la imagen Docker y despliegue.
- **ADR** sugeridos:
  1. Firebase para identidad.
  2. Cola en Postgres en vez de Redis.
  3. Token de Ballchasing por usuario.
  4. Guardar solo métricas seleccionadas.
  5. Neon + Render como hosting gratuito.

## 12. Despliegue gratuito y límites

| Pieza | Servicio | Límites a vigilar |
|---|---|---|
| API | Render (Docker) | Se duerme a los 15 min; 750 horas gratis/mes; reinicios posibles; sistema de archivos efímero |
| Base de datos | Neon | 100 CU-horas/mes por proyecto; escala a cero a los 5 min; almacenamiento 0,5–1 GB |
| Identidad | Firebase Auth (Spark) | 3000 usuarios activos/día sin facturación; 150 emails de reset/día |
| Frontend | GitHub Pages | Sitio estático |
| CI y cron | GitHub Actions | Minutos gratuitos según repo público/privado |

**No usar** el Postgres gratuito de Render: caduca a los 30 días.

Comprobar antes de empezar: que Render permita desplegar con Dockerfile en el plan gratuito y los minutos de Actions de tu cuenta.

## 13. Estructura del repositorio

```
boostlog/
├── backend/
│   ├── app/
│   │   ├── api/            # routers
│   │   ├── core/           # config, seguridad, logging
│   │   ├── db/             # modelos, sesión, migraciones
│   │   ├── services/       # ballchasing, sync, stats
│   │   └── worker/         # consumo de sync_jobs
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/               # React + Vite + TS
├── docs/
│   ├── adr/
│   └── api.md
├── docker-compose.yml
└── .github/workflows/
```

## 14. Fases

**Fase 0 — Esqueleto y despliegue temprano**
- [ ] Repo, `pyproject`, `ruff`, `pre-commit`
- [ ] FastAPI con `/health`, Dockerfile, `docker-compose` (api + postgres)
- [ ] CI básico
- [ ] Despliegue "hola mundo" en Render + Neon para validar la infraestructura gratuita

**Fase 1 — Usuarios y auth**
- [ ] Proyecto Firebase con email/contraseña y Google
- [ ] Verificación de ID token en FastAPI
- [ ] Modelo `users`, `GET /me`, `DELETE /me`
- [ ] Tests de auth

**Fase 2 — Credenciales y cuentas de juego**
- [ ] Cifrado del token y validación contra Ballchasing
- [ ] Endpoints de token y `game_accounts`
- [ ] Comprobar con una petición real los filtros del listado

**Fase 3 — Ingesta**
- [ ] Cliente Ballchasing con rate limiter y reintentos
- [ ] Tablas de replays y `player_stats` con migraciones
- [ ] Cola `sync_jobs` y worker
- [ ] `/sync`, `/sync/status` y cron de GitHub Actions
- [ ] Tests de idempotencia y de 429

**Fase 4 — API de estadísticas**
- [ ] `/replays`, `/replays/{id}`
- [ ] `/stats/summary` y `/stats/trends` (SQL con `date_trunc`)
- [ ] Índices y revisión de rendimiento

**Fase 5 — Frontend**
- [ ] Login con Firebase, guardado de token de Ballchasing, estado de sincronización
- [ ] Panel con tendencias (recharts o d3) y listado de partidas
- [ ] Despliegue en GitHub Pages y CORS

**Fase 6 — Observabilidad y cierre**
- [ ] Logs estructurados y `/metrics`
- [ ] Prometheus + Grafana en local
- [ ] README con arquitectura, decisiones y capturas; ADR completados

## 15. Riesgos

- Los términos o límites de Ballchasing, Render, Neon o Firebase pueden cambiar.
- El servicio dormido puede retrasar la primera petición alrededor de un minuto.
- Almacenamiento gratuito limitado: mantener el modelo compacto y considerar borrar datos antiguos.
- Replays antiguos sin algunas métricas: las gráficas deben tolerar valores nulos.

## 16. Decisiones abiertas

- Nombre definitivo del proyecto.
- Librería de gráficas (recharts o d3).
- Verificación de tokens: `firebase-admin` o validación directa con claves públicas de Google.
- Política de retención de datos (por ejemplo, borrar replays con más de N meses).