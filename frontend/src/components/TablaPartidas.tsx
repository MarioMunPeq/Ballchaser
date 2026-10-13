/** Listado de partidas, en formato tabla en escritorio y tarjetas en movil. */

import type { ReplayResumen } from "../lib/api";
import { fechaCorta, nombrePlaylist, numero, resultado } from "../lib/format";

interface Props {
  partidas: ReplayResumen[];
}

export function TablaPartidas({ partidas }: Props) {
  if (partidas.length === 0) {
    return <p className="vacio">No hay partidas con estos filtros.</p>;
  }

  return (
    <div className="tabla-envoltorio">
      <table className="tabla">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Playlist</th>
            <th>Mapa</th>
            <th>Resultado</th>
            <th className="num">Punt.</th>
            <th className="num">G</th>
            <th className="num">A</th>
            <th className="num">Par</th>
            <th className="num">BPM</th>
            <th className="num">Centros</th>
          </tr>
        </thead>
        <tbody>
          {partidas.map((p) => (
            <tr key={p.id}>
              <td data-etiqueta="Fecha">{fechaCorta(p.played_at, true)}</td>
              <td data-etiqueta="Playlist">{nombrePlaylist(p.playlist_id, p.playlist_name)}</td>
              <td data-etiqueta="Mapa" className="truncar">{p.map_name ?? "—"}</td>
              <td data-etiqueta="Resultado">
                <span className={`insignia ${p.result}`}>{resultado(p.result)}</span>
              </td>
              <td data-etiqueta="Punt." className="num">{numero(p.score)}</td>
              <td data-etiqueta="G" className="num">{numero(p.goals)}</td>
              <td data-etiqueta="A" className="num">{numero(p.assists)}</td>
              <td data-etiqueta="Par" className="num">{numero(p.saves)}</td>
              <td data-etiqueta="BPM" className="num">{numero(p.bpm)}</td>
              <td data-etiqueta="Centros" className="num">{numero(p.centers)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}