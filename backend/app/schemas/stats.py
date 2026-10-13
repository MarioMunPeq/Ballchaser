"""Esquemas de estadisticas agregadas."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class Metrica(StrEnum):
    """Metricas que se pueden pedir en `/stats/trends`.

    Es una lista cerrada a proposito: el valor llega del cliente y se usa para elegir
    una columna. Aceptar el nombre de la columna tal cual seria una inyeccion de SQL
    esperando a ocurrir.
    """

    SCORE = "score"
    GOALS = "goals"
    ASSISTS = "assists"
    SAVES = "saves"
    SHOTS = "shots"
    BPM = "bpm"
    AVG_AMOUNT = "avg_amount"
    PERCENT_ZERO_BOOST = "percent_zero_boost"
    PERCENT_FULL_BOOST = "percent_full_boost"
    AVG_SPEED = "avg_speed"
    PERCENT_SUPERSONIC_SPEED = "percent_supersonic_speed"
    PERCENT_GROUND = "percent_ground"
    PERCENT_LOW_AIR = "percent_low_air"
    PERCENT_HIGH_AIR = "percent_high_air"
    PERCENT_DEFENSIVE_THIRD = "percent_defensive_third"
    PERCENT_OFFENSIVE_THIRD = "percent_offensive_third"
    PERCENT_BEHIND_BALL = "percent_behind_ball"
    PERCENT_MOST_BACK = "percent_most_back"
    PERCENT_MOST_FORWARD = "percent_most_forward"
    DEMOS_INFLICTED = "demos_inflicted"
    DEMOS_TAKEN = "demos_taken"
    EPIC_SAVES = "epic_saves"
    CLEARS = "clears"
    CENTERS = "centers"
    AERIAL_HITS = "aerial_hits"
    FIRST_TOUCHES = "first_touches"
    FLIP_RESETS = "flip_resets"


class Intervalo(StrEnum):
    """Agrupaciones temporales disponibles."""

    DIA = "day"
    SEMANA = "week"
    MES = "month"


class ResumenStats(BaseModel):
    """Agregados del usuario en un rango de fechas."""

    replays: int = Field(description="Partidas jugadas en el rango.")
    wins: int
    losses: int
    ties: int

    win_rate: float | None = Field(
        default=None, description="Porcentaje de victorias, sin contar empates."
    )

    goals: int = Field(default=0, description="Goles marcados en total.")
    goals_against: int = Field(default=0, description="Goles encajados en total.")
    assists: int = Field(default=0)
    saves: int = Field(default=0)
    shots: int = Field(default=0)
    demos_inflicted: int = Field(default=0)
    demos_taken: int = Field(default=0)

    avg_score: float | None = None
    avg_bpm: float | None = None
    avg_percent_full_boost: float | None = None
    avg_percent_zero_boost: float | None = None
    avg_percent_supersonic_speed: float | None = None
    avg_percent_ground: float | None = None
    avg_duration: float | None = Field(
        default=None, description="Duracion media de las partidas, en segundos."
    )

    por_playlist: list["StatsPorPlaylist"] = Field(default_factory=list)


class StatsPorPlaylist(BaseModel):
    playlist_id: str
    playlist_name: str | None = None
    replays: int
    wins: int
    win_rate: float | None = None
    avg_score: float | None = None
    avg_bpm: float | None = None


class PuntoTendencia(BaseModel):
    """Un punto de la serie temporal."""

    periodo: date = Field(description="Inicio del dia, semana o mes.")
    valor: float | None = Field(
        default=None,
        description="Media de la metrica en el periodo. None si no hay datos.",
    )
    total: float | None = Field(default=None, description="Suma de la metrica.")
    replays: int = Field(description="Partidas en el periodo.")


class TendenciaRespuesta(BaseModel):
    metrica: Metrica
    intervalo: Intervalo
    puntos: list[PuntoTendencia] = Field(default_factory=list)


ResumenStats.model_rebuild()
