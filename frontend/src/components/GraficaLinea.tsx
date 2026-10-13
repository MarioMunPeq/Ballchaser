/**
 * Grafica de linea con D3 para las escalas y React para el DOM.
 *
 * Se elige esta via en vez de `d3.select()` sobre el SVG porque React ya gestiona el
 * DOM: lo que se hereda de D3 son las escalas, los ejes y la forma de la linea, que es
 * donde de verdad esta el trabajo matematico.
 */

import { extent, max, min } from "d3-array";
import { scaleLinear, scaleTime } from "d3-scale";
import { area, curveMonotoneX, line } from "d3-shape";
import { useMemo } from "react";

import { escalaEje, numero, type PuntoGrafica } from "../lib/format";

interface Props {
  puntos: PuntoGrafica[];
  /** Texto accesible y etiqueta del valor final. */
  etiqueta: string;
  /** Formatea los valores del eje. */
  formato?: (v: number) => string;
  /** Resaltar el último punto. */
  destacarUltimo?: boolean;
}

const MARGEN = { arriba: 12, derecha: 12, abajo: 26, izquierda: 42 };
const ALTO = 200;
const ANCHO = 320;

export function GraficaLinea({
  puntos,
  etiqueta,
  formato = numero,
  destacarUltimo = true,
}: Props) {
  const { trazo, areaTrazo, escalaY, escalaX, ticksY, ticksX, ultimo } = useMemo(() => {
    if (puntos.length === 0) {
      return {
        trazo: "",
        areaTrazo: "",
        escalaY: () => 0,
        escalaX: () => 0,
        ticksY: [] as number[],
        ticksX: [] as Date[],
        ultimo: null as PuntoGrafica | null,
      };
    }

    const [xMin, xMax] = extent(puntos, (p) => p.x) as [number, number];
    const yValues = puntos.map((p) => p.y);
    const yMin = min(yValues) ?? 0;
    const yMax = max(yValues) ?? 0;
    const dominio = escalaEje(yMin, yMax);

    // Un solo punto no dibuja una recta: se ensancha el dominio X para que quede en el
    // centro en vez de en una esquina.
    const x0 = xMin === xMax ? xMin - 86400000 : xMin;
    const x1 = xMin === xMax ? xMax + 86400000 : xMax;

    const y = scaleLinear()
        .domain([dominio.min, dominio.max])
        .range([ALTO - MARGEN.abajo, MARGEN.arriba]);
    const x = scaleTime().domain([x0, x1]).range([MARGEN.izquierda, ANCHO - MARGEN.derecha]);

    // `curveMonotoneX` evita que la recta "sobrepase" entre puntos y exagere las
    // subidas que no existen.
    const forma = line<PuntoGrafica>()
      .x((p) => x(p.x))
      .y((p) => y(p.y))
      .curve(curveMonotoneX);

    return {
      trazo: forma(puntos) ?? "",
      areaTrazo: area<PuntoGrafica>()
        .x((p) => x(p.x))
        .y0(y(dominio.min))
        .y1((p) => y(p.y))(puntos) ?? "",
      escalaY: y,
      escalaX: x,
      ticksY: y.ticks(4),
      ticksX: x.ticks(4),
      ultimo: puntos[puntos.length - 1] ?? null,
    };
  }, [puntos]);

  if (puntos.length === 0) {
    return (
      <p className="vacio">
        Todavia no hay datos para esta metrica. Sincroniza replays o cambia de rango.
      </p>
    );
  }

  return (
    <figure className="grafica">
      <svg
        viewBox={`0 0 ${ANCHO} ${ALTO}`}
        role="img"
        aria-label={`Grafica de tendencia: ${etiqueta}`}
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <linearGradient id="degradado-linea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--acento)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--acento)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {ticksY.map((t) => (
          <g key={`y-${t}`}>
            <line
              className="rejilla"
              x1={MARGEN.izquierda}
              x2={ANCHO - MARGEN.derecha}
              y1={escalaY(t)}
              y2={escalaY(t)}
            />
            <text className="eje-texto" x={MARGEN.izquierda - 6} y={escalaY(t) + 3} textAnchor="end">
              {formato(t)}
            </text>
          </g>
        ))}

        <path d={areaTrazo} fill="url(#degradado-linea)" />
        <path className="linea" d={trazo} />

        {puntos.map((p) => (
          <circle
            key={p.x}
            className="punto"
            cx={escalaX(p.x)}
            cy={escalaY(p.y)}
            r={destacarUltimo && p === ultimo ? 4 : 2.5}
          >
            <title>{`${p.etiqueta}: ${formato(p.y)} (${p.replays} partidas)`}</title>
          </circle>
        ))}

        {ticksX.map((t) => (
          <text
            key={`x-${t.getTime()}`}
            className="eje-texto"
            x={escalaX(t)}
            y={ALTO - 8}
            textAnchor="middle"
          >
            {t.toLocaleDateString("es-ES", { day: "numeric", month: "short" })}
          </text>
        ))}
      </svg>
    </figure>
  );
}