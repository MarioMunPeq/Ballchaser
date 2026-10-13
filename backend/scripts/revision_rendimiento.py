"""Revision de rendimiento con volumen realista.

Con una fila, Postgres elige siempre_seq scan_ y el plan no dice nada. Se generan
unas miles de partidas de un usuario de prueba, se miran los planes y se limpia todo.

    python scripts/revision_rendimiento.py
"""

import asyncio

from sqlalchemy import literal_column, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GameAccount, PlayerStat, Replay, User, UserReplay
from app.db.session import SessionLocal, engine
from app.services import stats as servicio_stats

PREFIX = "perf"
CUANTIDAD = 3000
RESULTADOS = ["win", "loss", "tie"]
PLAYLISTS = ["ranked-duels", "ranked-standard", "ranked-doubles", "casual"]


def _id(indice: int) -> str:
    return f"{PREFIX}{indice:029d}"


async def limpiar(session: AsyncSession) -> None:
    """Borra todo lo que creo este script."""
    patron = {"prefijo": f"{PREFIX}%"}
    for tabla, columna in (
        ("player_stats", "replay_id"),
        ("user_replays", "replay_id"),
        ("replays", "ballchasing_id"),
        ("users", "firebase_uid"),
    ):
        await session.execute(
            text(f"DELETE FROM {tabla} WHERE {columna} LIKE :prefijo"),  # noqa: S608
            patron,
        )
    await session.commit()


async def poblar(session: AsyncSession) -> str:
    await limpiar(session)

    user = User(email="perf@example.com", firebase_uid=f"{PREFIX}-user")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    cuenta = GameAccount(user_id=user.id, platform="steam", platform_id="perf-id")
    session.add(cuenta)
    await session.commit()
    await session.refresh(cuenta)

    replays, stats, vinculos = [], [], []
    for indice in range(CUANTIDAD):
        replay_id = _id(indice)
        replays.append(
            Replay(
                ballchasing_id=replay_id,
                played_at=date_de(indice),
                playlist_id=PLAYLISTS[indice % len(PLAYLISTS)],
                playlist_name=PLAYLISTS[indice % len(PLAYLISTS)],
                map_code="dfh_stadium",
                map_name="DFH Stadium",
                duration=380,
                play_duration=350,
                season=24,
                blue_goals=3,
                orange_goals=2,
            )
        )
        stats.append(
            PlayerStat(
                replay_id=replay_id,
                platform="steam",
                platform_id="perf-id",
                name="Perf",
                team="blue",
                score=400 + indice % 300,
                goals=indice % 4,
                bpm=350 + indice % 120,
                percent_full_boost=20.0 + (indice % 15),
                centers=indice % 6,
            )
        )
        vinculos.append(
            UserReplay(
                user_id=user.id,
                replay_id=replay_id,
                game_account_id=cuenta.id,
                team="blue",
                result=RESULTADOS[indice % 3],
            )
        )

    # Sin `relationship()` entre modelos, la unidad de trabajo no conoce el orden de
    # las claves foraneas: se inserta tabla a tabla, como hace la ingesta real.
    session.add_all(replays)
    await session.commit()
    session.add_all(stats)
    await session.commit()
    session.add_all(vinculos)
    await session.commit()

    await session.execute(text("ANALYZE"))
    await session.commit()
    return str(user.id)


def date_de(indice: int) -> object:
    from datetime import UTC, datetime, timedelta

    return datetime(2026, 10, 1, tzinfo=UTC) - timedelta(days=indice * 1.4, minutes=indice % 60)


async def _explicar(sentencia: object, etiqueta: str) -> None:
    async with engine.connect() as conn:
        compilada = sentencia.compile(  # type: ignore[attr-defined]
            conn.engine, compile_kwargs={"literal_binds": True}
        )
        filas = await conn.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {compilada}"))
        print(f"  [{etiqueta}]")
        for fila in filas:
            linea = fila[0]
            if any(p in linea for p in ("Scan", "Aggregate", "Sort", "never executed")):
                print(f"    {linea}")


async def main() -> None:
    async with SessionLocal() as session:
        user_id = await poblar(session)
        print(f"pobladas {CUANTIDAD} partidas")

        print("\n== listado: 50 partidas ordenadas por fecha ==")
        consulta = servicio_stats._aplicar(
            servicio_stats._base(user_id), servicio_stats.FiltroPartidas()
        )
        await _explicar(consulta.order_by(Replay.played_at.desc()).limit(50), "listado")

        print("\n== listado filtrado por playlist y fecha ==")
        from datetime import UTC, datetime

        filtro = servicio_stats.FiltroPartidas(
            playlist="ranked-duels", desde=datetime(2026, 6, 1, tzinfo=UTC)
        )
        await _explicar(
            servicio_stats._aplicar(servicio_stats._base(user_id), filtro)
            .order_by(Replay.played_at.desc())
            .limit(50),
            "filtrado",
        )

        print("\n== resumen global ==")
        await _explicar(
            servicio_stats._aplicar(servicio_stats._base(user_id), servicio_stats.FiltroPartidas()),
            "resumen",
        )

        print("\n== serie temporal por semana ==")
        periodo = literal_column("date_trunc('week', replays.played_at)")
        await _explicar(
            servicio_stats._aplicar(servicio_stats._base(user_id), servicio_stats.FiltroPartidas())
            .with_only_columns(
                periodo.label("periodo"),
                literal_column("avg(player_stats.bpm)").label("valor"),
                literal_column("count(distinct user_replays.replay_id)").label("replays"),
            )
            .group_by(periodo)
            .order_by(periodo),
            "tendencias",
        )

        print("\n== medidas ==")
        medidas = (
            "SELECT "
            "(SELECT count(*) FROM replays) AS replays, "
            "(SELECT count(*) FROM player_stats) AS player_stats, "
            "(SELECT count(*) FROM user_replays) AS user_replays, "
            "(SELECT pg_size_pretty(pg_total_relation_size('replays'))) AS tam_replays, "
            "(SELECT pg_size_pretty(pg_total_relation_size('player_stats'))) AS tam_stats"
        )
        fila = (await session.execute(text(medidas))).one()
        print(f"  filas -> {fila._mapping}")
        print("  mide una partida real de este proyecto como orden de magnitud.")

        await limpiar(session)
        print("\nlimpiado")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
