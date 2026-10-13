# La API de Ballchasing, comprobada contra el servicio real

Todo lo de este documento se verifico con peticiones reales (token de desarrollo,
octubre 2026). La guia original dejaba algunos detalles por suponer; estos son
los que se han visto de verdad. Donde contradice a la guia, manda esto.

## 1. Cabecera de autenticacion

`Authorization: <token>` (sin `Bearer`). Un token invalido devuelve:

```
401 {"error": "invalid API key", ...}
```

**No existe endpoint de perfil.** Ni `/me`, ni `/accounts/me`, ni `/users/me`: todos 404.
La forma mas barata de validar un token es por tanto una llamada al listado
(`GET /replays?count=1&uploader=me`), que cuesta 1 de las 500 llamadas/hora.

## 2. Listado: `GET /replays`

La respuesta **no** tiene `replays` ni `meta`:

```json
{ "list": [ ... ], "count": 10000, "next": "https://ballchasing.com/api/replays?after=..." }
```

| Parametro | Comprobado |
|---|---|
| `count` | maximo **200**. `count=250` -> `400 invalid param "count"` |
| **`player-id`** | **`steam:76561199085282414`**: devuelve las partidas en las que **jugo** esa persona, la suba quien la suba. Acepta varios (`&player-id=...&player-id=...`) |
| `player-name` | funciona, pero por nombre: si el jugador cambia de nombre se le pierde |
| `uploader=me` | **funciona solo**, sin `player-name` (200). Devuelve solo lo que subi **esa** cuenta |
| `uploader=<SteamID64>` | acepta tambien el id numerico |
| `playlist` | **identificador**, no nombre: `unranked-standard` vale; `casual` y `1` dan `400 invalid "playlist"` |
| `season` | entero, `24` responde bien |
| `replay-date-after` / `-before` | **RFC3339**: `2026-01-01` falla con `must be in RFC3339 format`; `2026-01-01T00:00:00Z` vale |
| `created-before` / `created-after` | filtros aparte, de la fecha de **subida**, no de la partida |
| `next` | URL absoluta que devuelve la propia API |

### El filtro que cambia el diseno: `player-id`

Pedir `GET /replays?player-id=steam:76561199085282414` devolvio **1578 replays** de un
jugador, y venian de subiadores distintos (`Rob`, `plumato`...).

Consecuencia: **el usuario no tiene que subir sus propias partidas.** Basta con que
registre su cuenta de juego (`steam:<su id>`) y la aplicacion encuentra todas las
partidas en las que jugó, las suba quien las suba. Es mejor que subir replays, y ademas
la guia dejaba la subida fuera de alcance.

Por eso la ingesta seguiere por `player-id` a partir de `game_accounts`, no por
`uploader=me`.

### `player-name` frente a `player-id`

Los dos funcionan, pero por nombre es frágil: un jugador que cambia su nombre en Steam
desaparece del historico. El identificador de plataforma no cambia. Siempre que se pueda,
`player-id`.

### Trampa: `count` + `next` rompe el cursor

Si se sigue `next` **añadiendo** parametros, el cursor se ignora en silencio y se vuelve
a la primera pagina:

```
GET /replays?count=3                      -> [A, B, C]
GET <next tal cual>                       -> [D, E, F]   correcto
GET /replays?count=3&next=<cursor>        -> [A, B, C]   el cursor se ignora
```

Regla: **el enlace `next` se sigue literalmente, sin tocarlo.**

## 3 bis. Subir replays (fuera de alcance, pero existe)

Hay endpoint de subida: `POST /api/v2/upload?visibility=public|unlisted|private|group`,
con `multipart/form-data` y el fichero `.replay` en el campo `file`. Devuelve `201` con
el id de la partida creada, o `409` si ya existe.

Sin fichero responde `400 failed to get multipart form: request Content-Type isn't
multipart/form-data`, lo que confirma el metodo y el formato.

La v1 **no** lo usa: el usuario ya sube sus replays como haga, y con `player-id` no hace
falta ni que lo haga.

## 3. Detalle: `GET /replays/{id}`

Respuesta **plana**, sin envoltorio `replay`. Los equipos son **diccionarios**, no listas:

```json
{
  "id": "...", "status": "ok", "team_size": 3, "match_type": "Online",
  "playlist_id": "unranked-standard", "season": 24, "season_type": "free2play",
  "date": "2026-10-13T04:44:29Z", "duration": 370, "play_duration": 347, "overtime": false,
  "uploader": { "steam_id": "...", "name": "...", ... },
  "blue":   { "color": "blue",   "players": [ ... ], "stats": { ... } },
  "orange": { "color": "orange", "players": [ ... ], "stats": { ... } }
}
```

`status` es `ok` (25 de 25 replays comprobados). Se espera `pending`/`failed` en replays
a medio procesar; la ingesta debe saltarselos.

### Cada jugador

```json
{
  "name": "S0LR",
  "id": { "platform": "steam", "id": "76561199085282414" },
  "mvp": true,
  "stats": { "core": {...}, "boost": {...}, "movement": {...}, "positioning": {...}, "demo": {...} }
}
```

- El identificador es `id.platform` + `id.id`, **no** `platform` + `platform_id` en plano.
- `mvp` **solo aparece en el jugador MVP**. En los demas la clave no existe: hay que
  tratarlo como nullable, no como booleano por defecto.
- Las estadisticas van **anidadas por grupo**, no en columnas planas.

### Grupos de estadisticas (claves reales)

| Grupo | Nº | Claves |
|---|---|---|
| `core` | 18 | shots, shots_against, goals, goals_against, saves, assists, score, mvp, shooting_percentage, epic_saves, clears, centers, aerial_hits, first_touches, flip_resets, crossbar_hits, bicycle_hits, juggle_hits |
| `boost` | 28 | bpm, bcpm, avg_amount, amount_collected(+big/small), amount_stolen(+big/small), amount_overfill, amount_overfill_stolen, amount_used_while_supersonic, count_collected_big/small, count_stolen_big/small, time_zero_boost, percent_zero_boost, time_full_boost, percent_full_boost, time_boost_0_25/25_50/50_75/75_100, percent_boost_* |
| `movement` | 18 | avg_speed, avg_speed_percentage, total_distance, time_supersonic_speed, time_boost_speed, time_slow_speed, time_ground, time_low_air, time_high_air, time_powerslide, count_powerslide, avg_powerslide_duration, percent_supersonic_speed, percent_boost_speed, percent_slow_speed, percent_ground, percent_low_air, percent_high_air |
| `positioning` | 27 | avg_distance_to_ball(+possession/no_possession), avg_distance_to_mates, goals_against_while_last_defender, percent_behind_ball, percent_closest_to_ball, percent_defensive_half, percent_defensive_third, percent_farthest_from_ball, percent_infront_ball, percent_most_back, percent_most_forward, percent_neutral_third, percent_offensive_half, percent_offensive_third, percent_*, time_* (mismos nombres) |
| `demo` | 6 | inflicted, inflicted_in_defensive_half, inflicted_in_offensive_half, taken, taken_in_defensive_half, taken_in_offensive_half |

**El grupo se llama `demo` en singular, y sus claves no llevan el prefijo `demos_`** que
suponia la guia (`demos_inflicted_def_half` -> aqui es `demo.inflicted_in_defensive_half`).

Los grupos de equipo (`blue.stats`, `orange.stats`) tienen ademas `ball`, y usan los mismos
nombres de grupo.

## 4. Identificadores utiles

El listado incluye `rocket_league_id` (identificador de la partida en el juego) y el bloque
`uploader` con `steam_id` y `name`. Sirve para emparejar una partida con un jugador sin
depender del nombre, que puede cambiar.

Un usuario puede averiguar su SteamID64 en la URL de su perfil de Steam:
`https://steamcommunity.com/profiles/76561199085282414/`. Es el dato que va en
`game_accounts.platform_id`, y con el forma `steam:76561199085282414` para el filtro
`player-id`.

## 5. Limites observados

Los de la guia se cumplen, pero el **listado es el endpoint que primero castiga**: a 10
peticiones seguidas devolvio `429` con un cuerpo de broma de Rocket League incrustado en
el campo `error`. El cliente tiene que distinguir el 429 real (por cabecera/estado) y no
fiarse del texto.