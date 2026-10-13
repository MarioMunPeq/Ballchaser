"""Replays, su pertenencia a un usuario y las estadisticas de ese jugador.

Decisiones que se apartan de un "guardo todo lo que me dan":

- Solo se guardan las estadisticas de los jugadores que **pertenecen al usuario**
  (`game_accounts`). Una partida tiene entre 6 y 10 jugadores y la v1 no compara
  usuarios (esta fuera de alcance), asi que el resto solo ocuparia espacio.
- Se guardan metricas seleccionadas, no el JSON entero: cabe en el almacenamiento
  gratuito de Neon y las agregaciones son simples.

Ver `docs/adr/0004-solo-metricas-seleccionadas.md`.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UtcDateTime


class Replay(Base):
    """Una partida, identificada por su id en Ballchasing.

    Esa id como clave primaria es lo que hace la ingesta idempotente: una partida ya
    guardada se descarta con un `ON CONFLICT DO NOTHING`, y el worker puede morir y
    repetirse sin duplicar nada.
    """

    __tablename__ = "replays"

    ballchasing_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    played_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
    rocket_league_id: Mapped[str | None] = mapped_column(String(64))
    playlist_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    playlist_name: Mapped[str | None] = mapped_column(String(64))
    map_code: Mapped[str | None] = mapped_column(String(64))
    map_name: Mapped[str | None] = mapped_column(String(64))
    team_size: Mapped[int | None] = mapped_column(Integer)
    duration: Mapped[int | None] = mapped_column(Integer)
    play_duration: Mapped[int | None] = mapped_column(Integer)
    overtime: Mapped[bool | None] = mapped_column(Boolean)
    season: Mapped[int | None] = mapped_column(Integer)
    season_type: Mapped[str | None] = mapped_column(String(32))
    blue_goals: Mapped[int | None] = mapped_column(Integer)
    orange_goals: Mapped[int | None] = mapped_column(Integer)

    def __repr__(self) -> str:
        return f"<Replay {self.ballchasing_id} {self.playlist_id}>"


class UserReplay(Base):
    """Une una partida con el usuario, su cuenta de juego y su resultado."""

    __tablename__ = "user_replays"
    __table_args__ = (
        UniqueConstraint("user_id", "replay_id", name="uq_user_replays_user_replay"),
        Index("ix_user_replays_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    replay_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("replays.ballchasing_id", ondelete="CASCADE"), nullable=False
    )
    game_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("game_accounts.id", ondelete="CASCADE"), nullable=False
    )
    # 'blue' u 'orange'
    team: Mapped[str] = mapped_column(String(8), nullable=False)
    # 'win', 'loss', 'tie' (tie = prolongation resuelta en penaltis)
    result: Mapped[str] = mapped_column(String(8), nullable=False)

    def __repr__(self) -> str:
        return f"<UserReplay user={self.user_id} replay={self.replay_id} {self.result}>"


class PlayerStat(Base):
    """Estadisticas de **un** jugador en una partida.

    Solo se guardan las de los jugadores del usuario (ver la nota del modulo). Las
    columnas vienen anidadas en la API (`stats.core.bpm`...) y se aplanan aqui.

    Las columnas nullable son las que Ballchasing solo rellena en replays recientes:
    `epic_saves`, `clears`, `centers`, `aerial_hits`, `first_touches`, `flip_resets` y
    los demos por mitad. En replays viejos son `None` y las graficas tienen que
    tolerarlo.
    """

    __tablename__ = "player_stats"

    replay_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("replays.ballchasing_id", ondelete="CASCADE"), primary_key=True
    )
    platform: Mapped[str] = mapped_column(String(16), primary_key=True)
    platform_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    name: Mapped[str | None] = mapped_column(String(64))
    team: Mapped[str | None] = mapped_column(String(8))
    # La API solo incluye `mvp` en el jugador MVP: en el resto la clave no existe.
    mvp: Mapped[bool | None] = mapped_column(Boolean)

    # core
    score: Mapped[int | None] = mapped_column(Integer)
    goals: Mapped[int | None] = mapped_column(Integer)
    assists: Mapped[int | None] = mapped_column(Integer)
    saves: Mapped[int | None] = mapped_column(Integer)
    shots: Mapped[int | None] = mapped_column(Integer)
    goals_against: Mapped[int | None] = mapped_column(Integer)
    shots_against: Mapped[int | None] = mapped_column(Integer)
    shooting_percentage: Mapped[float | None] = mapped_column(Float)

    # boost
    bpm: Mapped[int | None] = mapped_column(Integer)
    avg_amount: Mapped[float | None] = mapped_column(Float)
    percent_zero_boost: Mapped[float | None] = mapped_column(Float)
    percent_full_boost: Mapped[float | None] = mapped_column(Float)
    amount_stolen: Mapped[int | None] = mapped_column(Integer)

    # movement
    avg_speed: Mapped[int | None] = mapped_column(Integer)
    percent_supersonic_speed: Mapped[float | None] = mapped_column(Float)
    percent_ground: Mapped[float | None] = mapped_column(Float)
    percent_low_air: Mapped[float | None] = mapped_column(Float)
    percent_high_air: Mapped[float | None] = mapped_column(Float)

    # positioning
    percent_defensive_third: Mapped[float | None] = mapped_column(Float)
    percent_offensive_third: Mapped[float | None] = mapped_column(Float)
    percent_behind_ball: Mapped[float | None] = mapped_column(Float)
    percent_most_back: Mapped[float | None] = mapped_column(Float)
    percent_most_forward: Mapped[float | None] = mapped_column(Float)

    # demos
    demos_inflicted: Mapped[int | None] = mapped_column(Integer)
    demos_taken: Mapped[int | None] = mapped_column(Integer)

    # Solo en replays recientes: pueden venir en None.
    epic_saves: Mapped[int | None] = mapped_column(Integer)
    clears: Mapped[int | None] = mapped_column(Integer)
    centers: Mapped[int | None] = mapped_column(Integer)
    aerial_hits: Mapped[int | None] = mapped_column(Integer)
    first_touches: Mapped[int | None] = mapped_column(Integer)
    flip_resets: Mapped[int | None] = mapped_column(Integer)
    demos_inflicted_def_half: Mapped[int | None] = mapped_column(Integer)
    demos_inflicted_off_half: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<PlayerStat {self.platform}:{self.platform_id} replay={self.replay_id}>"
