/** Barras horizontales: victory rate y media de BPM por playlist. */

import { scaleLinear } from "d3-scale";
import { useMemo } from "react";

import type { StatsPorPlaylist } from "../lib/api";
import { nombrePlaylist, numero, porcentaje } from "../lib/format";

interface Props {
  datos: StatsPorPlaylist[];
  /** 'win_rate' usa el porcentaje de victorias; 'avg_bpm', la media de boost. */
  criterio: "win_rate" | "avg_bpm";
}

const ALTO_BARRA = 10;

export function GraficaPlaylist({ datos, criterio }: Props) {
  const maximo = useMemo(
    () => Math.max(...datos.map((d) => (criterio === "win_rate" ? (d.win_rate ?? 0) : (d.avg_bpm ?? 0))), 1),
    [datos, criterio],
  );
  const escala = useMemo(() => scaleLinear().domain([0, maximo]).range([0, 100]), [maximo]);

  if (datos.length === 0) {
    return <p className="vacio">Sin partidas por playlist todavia.</p>;
  }

  return (
    <div className="barras">
      {datos.map((dato) => {
        const valor = criterio === "win_rate" ? dato.win_rate : dato.avg_bpm;
        return (
          <div className="barra-fila" key={dato.playlist_id}>
            <span className="barra-nombre">{nombrePlaylist(dato.playlist_id, dato.playlist_name)}</span>
            <div className="barra-pista">
              <div
                className={`barra ${criterio === "win_rate" && (dato.win_rate ?? 0) >= 50 ? "buena" : "mala"}`}
                style={{ width: `${escala(valor ?? 0)}%`, height: ALTO_BARRA }}
                title={`${dato.wins} victorias de ${dato.replays} partidas`}
              />
            </div>
            <span className="barra-valor">
              {criterio === "win_rate" ? porcentaje(dato.win_rate, 0) : numero(dato.avg_bpm)}
              <small> · {dato.replays}</small>
            </span>
          </div>
        );
      })}
    </div>
  );
}