# 0004. Solo metricas seleccionadas y solo las del usuario

- Estado: Aceptada
- Fecha: 2026-10-13

## Contexto

Ballchasing devuelve el detalle de una partida con unas 100 metricas por jugador, en
cinco grupos (`core`, `boost`, `movement`, `positioning`, `demo`), y una partida tiene
entre 6 y 10 jugadores.

La v1 es un analizador de progreso personal. Las comparativas entre usuarios estan
**fuera de alcance** de forma explicita, asi que el 80% de esas filas no las va a leer
nadie. Y el alojamiento gratis de Neon esta entre 0,5 y 1 GB por proyecto: guardar todo
lo que llega es gastar ese margen en datos que nadie consulta.

Ademas hay una razon de privacidad: `player_stats` describe como juega una persona.
Guardar las de todos los jugadores de todas las partidas es guardar datos personales
de gente que ni siquiera se ha registrado en el servicio.

## Decision

1. **Solo metricas seleccionadas.** De los ~100 campos por jugador se guardan los que
   alimentan las graficas: nucleo, boost, movimiento, posicionamiento y demos. Se
   descarta lo demas: configuracion de camara, sensibilidad y desgloses detallados.
2. **Solo los jugadores del usuario.** Se identifican por `game_accounts`
   (platform + platform_id) y de los 6-10 jugadores de una partida solo se guardan sus
   filas de estadisticas.
3. **La partida si se guarda completa** (`replays`), porque es pequena y en la v1 solo
   la consultan las personas que jugado en ella.

## Consecuencias

A favor:

- Una partida ocupa una fila de `replays` y entre 1 y 2 de `player_stats`, no 10.
- Solo hay datos personales de gente que se ha registrado.
- Las agregaciones son simples: columnas planas y `date_trunc` en Postgres.

En contra:

- Si en el futuro se quisieran comparar con otros jugadores habria que volver a
  Ballchasing por las estadisticas que no se guardaron. Se acepta: se pueden reingerir.
- Un jugador no puede "descubrir" a sus rivales a partir de la base de datos.

Lo que descarta esta decision:

- Guardar el JSON completo de cada replay.
- Analisis deelian team, mostrados en tablas.
- Cualquier comparativa entre usuarios sin reingerir.