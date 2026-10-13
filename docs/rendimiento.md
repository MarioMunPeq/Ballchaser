# Rendimiento de las consultas

Medido con `backend/scripts/revision_rendimiento.py`, que genera 3000 partidas de un
usuario de prueba en Postgres, mira el plan de las consultas de la API y limpia todo
despues.

## Resultado

Con 3000 partidas de un usuario:

| Consulta | Plan | Tiempo real |
|---|---|---|
| Listado sin filtro | seq scan en `user_replays` + index scan en `player_stats_pkey` | ~0,7 ms |
| Listado con `playlist` y fecha | **bitmap index scan** en `ix_replays_playlist_id` e `ix_replays_played_at` | ~0,8 ms |
| Resumen global | seq scan en las tres tablas (agrega todas) | ~1,0 ms |
| Serie temporal por semana | `GroupAggregate` sobre las 3000 filas | ~5,1 ms |

Los indices hacen su trabajo en el caso filtrado, que es el que se repite al paginar.
El resumen y las tendencias recorren todos los datos del usuario a proposito (son
agregados): ahi un indice adicional no ayudaria, solo anadiria escritura.

## Tamaño en disco

| Tabla | Filas | Tamaño | Por fila |
|---|---|---|---|
| `replays` | 3000 | 1856 kB | ~0,6 kB |
| `player_stats` | 3000 | 1536 kB | ~0,5 kB |

Una partida con las estadisticas de un jugador ocupa alrededor de **1,1 kB**. Con el
almacenamiento gratis de Neon (0,5-1 GB) caben del orden de **500.000 partidas por
usuario**, muy por encima del historico real de nadie.

Esto confirma la decision del [ADR 0004](adr/0004-solo-metricas-seleccionadas.md):
guardar solo metricas seleccionadas y solo las del usuario no es una decision de
principio, es tambien lo que cabe en el presupuesto.

## Por que SQLite no Sirve para esto

Con una fila, Postgres elige siempre un seq scan y el plan no dice absolutamente nada.
Por eso los tests corren rapido en SQLite (que es lo que se busca) pero la revision de
rendimiento se hace aparte y contra Postgres.

Ademas, SQLite acepta cosas que Postgres rechaza: un `GROUP BY` invalido, un
`varchar(36)` mas largo, claves foraneas sin comprobar. Varios bugs de la API de datos
solo aparecieron al correr la suite contra Postgres, no en SQLite. Por eso el job
`backend-postgres` de CI no es un adorno.