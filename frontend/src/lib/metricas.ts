/** Datos del panel: metricas que se Pintan como KPI y como gráfica. */

import type { ResumenStats } from "./api";

export interface MetricaKpi {
  clave: string;
  etiqueta: string;
  valor: string;
  detalle?: string;
  /** Se usa para decidir si el numero es "bueno" (verde) o "malo" (rojo). */
  sentido?: "alto" | "bajo" | "neutro";
}

export function metricasDe(resumen: ResumenStats | null): MetricaKpi[] {
  if (!resumen) return [];

  return [
    {
      clave: "winrate",
      etiqueta: "Victorias",
      valor: resumen.win_rate === null ? "—" : `${resumen.win_rate} %`,
      detalle: `${resumen.wins} de ${resumen.replays} partidas`,
      sentido: "alto",
    },
    {
      clave: "bpm",
      etiqueta: "BPM medio",
      valor: resumen.avg_bpm === null ? "—" : String(Math.round(resumen.avg_bpm)),
      detalle: "boost por minuto",
      sentido: "alto",
    },
    {
      clave: "fullboost",
      etiqueta: "Boost lleno",
      valor: resumen.avg_percent_full_boost === null ? "—" : `${resumen.avg_percent_full_boost} %`,
      detalle: "porcentaje del tiempo con 100 de boost",
      sentido: "alto",
    },
    {
      clave: "goles",
      etiqueta: "Goles",
      valor: String(resumen.goals),
      detalle: `${resumen.goals_against} en contra`,
      sentido: "alto",
    },
    {
      clave: "paradas",
      etiqueta: "Paradas",
      valor: String(resumen.saves),
      detalle: `${resumen.shots} disparos enfrentados`,
      sentido: "alto",
    },
    {
      clave: "demos",
      etiqueta: "Demos",
      valor: String(resumen.demos_inflicted),
      detalle: `sufrió ${resumen.demos_taken}`,
      sentido: "alto",
    },
  ];
}

export interface MetricaTendencia {
  clave: string;
  etiqueta: string;
  /** Nombre exacto que espera `GET /stats/trends`. */
  api: string;
  /** `%` en el eje, si la metrica es un porcentaje. */
  esPorcentaje?: boolean;
  decimales?: number;
}

export const METRICAS_TENDENCIA: MetricaTendencia[] = [
  { clave: "bpm", etiqueta: "BPM", api: "bpm" },
  { clave: "percent_full_boost", etiqueta: "Boost lleno", api: "percent_full_boost", esPorcentaje: true, decimales: 1 },
  { clave: "percent_zero_boost", etiqueta: "Sin boost", api: "percent_zero_boost", esPorcentaje: true, decimales: 1 },
  { clave: "percent_supersonic_speed", etiqueta: "Velocidad supersónica", api: "percent_supersonic_speed", esPorcentaje: true, decimales: 1 },
  { clave: "percent_ground", etiqueta: "En suelo", api: "percent_ground", esPorcentaje: true, decimales: 1 },
  { clave: "avg_speed", etiqueta: "Velocidad media", api: "avg_speed" },
  { clave: "goals", etiqueta: "Goles", api: "goals", decimales: 1 },
  { clave: "assists", etiqueta: "Asistencias", api: "assists", decimales: 1 },
  { clave: "saves", etiqueta: "Paradas", api: "saves", decimales: 1 },
  { clave: "centers", etiqueta: "Centros", api: "centers", decimales: 1 },
  { clave: "demos_inflicted", etiqueta: "Demos", api: "demos_inflicted", decimales: 1 },
];