"""Esquemas de replays."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReplayResumen(BaseModel):
    """Una partida en la lista, con lo justo para pintar una fila."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    played_at: datetime
    playlist_id: str
    playlist_name: str | None = None
    map_code: str | None = None
    map_name: str | None = None
    blue_goals: int | None = None
    orange_goals: int | None = None
    team: str = Field(description="blue u orange: en que equipo juegas.")
    result: str = Field(description="win, loss o tie.")
    score: int | None = Field(default=None, description="Tu puntuacion en la partida.")
    goals: int | None = None
    assists: int | None = None
    saves: int | None = None
    bpm: int | None = Field(default=None, description="Boost por minuto.")
    # Viene en None en replays antiguos: la API solo lo rellena en replays recientes.
    centers: int | None = None


class PlayerStatsCompletas(BaseModel):
    """Estadisticas del usuario en una partida.

    Solo se guardan las del usuario que consulta (ADR 0004), asi que la respuesta no
    incluye las de los rivales aunque se pidieron a Ballchasing.
    """

    model_config = ConfigDict(from_attributes=True)

    platform: str
    platform_id: str
    name: str | None
    team: str | None
    mvp: bool | None

    score: int | None
    goals: int | None
    assists: int | None
    saves: int | None
    shots: int | None
    goals_against: int | None
    shots_against: int | None
    shooting_percentage: float | None

    bpm: int | None
    avg_amount: float | None
    percent_zero_boost: float | None
    percent_full_boost: float | None
    amount_stolen: int | None

    avg_speed: int | None
    percent_supersonic_speed: float | None
    percent_ground: float | None
    percent_low_air: float | None
    percent_high_air: float | None

    percent_defensive_third: float | None
    percent_offensive_third: float | None
    percent_behind_ball: float | None
    percent_most_back: float | None
    percent_most_forward: float | None

    demos_inflicted: int | None
    demos_taken: int | None

    epic_saves: int | None
    clears: int | None
    centers: int | None
    aerial_hits: int | None
    first_touches: int | None
    flip_resets: int | None
    demos_inflicted_def_half: int | None
    demos_inflicted_off_half: int | None


class ReplayDetalle(BaseModel):
    """Detalle de una partida con las estadisticas del usuario."""

    replay: ReplayResumen
    duration: int | None = None
    play_duration: int | None = None
    overtime: bool | None = None
    season: int | None = None
    season_type: str | None = None
    team_size: int | None = None
    stats: list[PlayerStatsCompletas] = Field(
        default_factory=list,
        description="Estadisticas guardadas del usuario (puede haber mas de una cuenta).",
    )


class ReplayPaginado(BaseModel):
    """Pagina de replays con el total, para que el frontend pueda paginar."""

    items: list[ReplayResumen]
    total: int = Field(description="Partidas que cumplen el filtro, sin contar el limite.")
    limit: int
    offset: int
