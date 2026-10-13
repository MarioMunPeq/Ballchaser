/**
 * Formateadores de la interfaz.
 *
 * Funciones puras y sin dependencias: son la parte del frontend que mas merece tener
 * tests, porque un `NaN` o un `undefined` en pantalla es un bug visible.
 *
 * Los numeros y las fechas se formatean **a mano** y no con `toLocaleString`. Es
 * deliberado: el resultado de `toLocaleString("es-ES")` depende de los datos de
 * idioma que traiga el runtime (Node con ICU reducido devuelve "1234" en vez de
 * "1.234"), asi que la misma pantalla se veria distinta segun donde corra.
 */

import type { PuntoTendencia } from "./api";

const SIN_DATO = "—";

const MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const MESES_LARGOS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

function parte_entera(texto: string): string {
  const negativo = texto.startsWith("-");
  const digitos = negativo ? texto.slice(1) : texto;
  // Se rellena hasta un multiplo de tres para poder partir en grupos, y luego se
  // quitan los ceros de relleno.
  const relleno = digitos.padStart(Math.ceil(digitos.length / 3) * 3, "0");
  const conPuntos = relleno.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const limpio = conPuntos.replace(/^0+(?=\d)/, "");
  return negativo ? `-${limpio}` : limpio;
}

export function numero(valor: number | null | undefined, decimales = 0): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return SIN_DATO;

  const fijo = valor.toFixed(decimales);
  const [entero, parte] = fijo.split(".");
  const conPuntos = entero === undefined ? fijo : parte_entera(entero);
  // En castellano el separador decimal es la coma.
  return parte ? `${conPuntos},${parte}` : conPuntos;
}

export function porcentaje(valor: number | null | undefined, decimales = 1): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return SIN_DATO;
  return `${numero(valor, decimales)} %`;
}

export function segundos(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return SIN_DATO;
  const minutos = Math.floor(valor / 60);
  const resto = Math.round(valor % 60);
  return `${minutos}:${String(resto).padStart(2, "0")}`;
}

function como_fecha(iso: string): Date | null {
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}

/** "1 mar" o "1 mar 2026" si se pide el año. */
export function fechaCorta(iso: string, conAnio = false): string {
  const fecha = como_fecha(iso);
  if (!fecha) return SIN_DATO;
  const base = `${fecha.getDate()} ${MESES_CORTOS[fecha.getMonth()] ?? ""}`;
  return conAnio ? `${base} ${fecha.getFullYear()}` : base;
}

export function fechaLarga(iso: string): string {
  const fecha = como_fecha(iso);
  if (!fecha) return SIN_DATO;
  return `${fecha.getDate()} ${MESES_LARGOS[fecha.getMonth()] ?? ""} ${fecha.getFullYear()}`;
}

export function haceCuanto(iso: string | null): string {
  if (!iso) return "nunca";
  const fecha = como_fecha(iso);
  if (!fecha) return SIN_DATO;

  const minutos = Math.round((Date.now() - fecha.getTime()) / 60000);
  if (minutos < 1) return "ahora mismo";
  if (minutos < 60) return `hace ${minutos} min`;

  const horas = Math.round(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;

  const dias = Math.round(horas / 24);
  return `hace ${dias} d`;
}

export function resultado(result: "win" | "loss" | "tie"): string {
  return { win: "Victoria", loss: "Derrota", tie: "Empate" }[result];
}

export function nombrePlaylist(playlistId: string, nombre?: string | null): string {
  if (nombre) return nombre;
  return playlistId.replaceAll("-", " ");
}

export interface PuntoGrafica {
  x: number;
  y: number;
  etiqueta: string;
  replays: number;
}

/**
 * Convierte la serie de la API en puntos para la escala lineal de d3.
 *
 * Filtra los puntos sin valor (metricas nulas en replays antiguos) en lugar de
 * tratarlos como cero: un 0 donde no se jugó hace que la gráfica baje de golpe y se
 * lea como una caída de rendimiento que no ocurrió.
 */
export function aPuntos(puntos: PuntoTendencia[]): PuntoGrafica[] {
  return puntos
    .filter((p): p is PuntoTendencia & { valor: number } => p.valor !== null)
    .map((p) => ({
      x: new Date(p.periodo).getTime(),
      y: p.valor,
      etiqueta: fechaCorta(p.periodo),
      replays: p.replays,
    }))
    .sort((a, b) => a.x - b.x);
}

/** Redondea el eje a "bonitos" (1, 2, 2.5, 5 x 10^n) para que las etiquetas se lean. */
export function escalaEje(min: number, max: number): { min: number; max: number } {
  if (min === max) {
    const margen = Math.abs(min) * 0.05 || 1;
    return { min: min - margen, max: max + margen };
  }

  const paso = (max - min) / 4;
  const magnitud = Math.pow(10, Math.floor(Math.log10(Math.abs(paso) || 1)));
  const pasoBonito = [1, 2, 2.5, 5, 10].map((m) => m * magnitud).find((p) => p >= paso) ?? 10 * magnitud;

  return {
    min: Math.floor(min / pasoBonito) * pasoBonito,
    max: Math.ceil(max / pasoBonito) * pasoBonito,
  };
}