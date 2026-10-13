import { useState } from "react";

import { FilaKpis } from "../components/FilaKpis";
import { GraficaLinea } from "../components/GraficaLinea";
import { GraficaPlaylist } from "../components/GraficaPlaylist";
import { TablaPartidas } from "../components/TablaPartidas";
import { useReplays, useResumen, useTendencia } from "../hooks/useApi";
import { aPuntos, numero, porcentaje } from "../lib/format";
import { METRICAS_TENDENCIA, metricasDe } from "../lib/metricas";

const RANGOS = [
  { clave: "", etiqueta: "Todo" },
  { clave: "7", etiqueta: "7 días" },
  { clave: "30", etiqueta: "30 días" },
  { clave: "90", etiqueta: "90 días" },
];

const INTERVALOS = [
  { clave: "day", etiqueta: "Día" },
  { clave: "week", etiqueta: "Semana" },
  { clave: "month", etiqueta: "Mes" },
];

export function PaginaPanel() {
  const [rango, setRango] = useState("");
  const [metrica, setMetrica] = useState(METRICAS_TENDENCIA[0]?.api ?? "bpm");
  const [intervalo, setIntervalo] = useState("week");

  const desde = rango ? new Date(Date.now() - Number(rango) * 86400000).toISOString().slice(0, 10) : undefined;

  const resumen = useResumen();
  const tendencia = useTendencia(metrica, intervalo);
  const replays = useReplays({ desde, limit: 25 });

  const definicion = METRICAS_TENDENCIA.find((m) => m.api === metrica);
  const puntos = tendencia.datos ? aPuntos(tendencia.datos.puntos) : [];

  return (
    <div className="pagina">
      <section className="tarjeta">
        <div className="tarjeta-cabecera">
          <h2>Resumen</h2>
          <div className="filtros" role="group" aria-label="Rango de fechas">
            {RANGOS.map((r) => (
              <button
                key={r.clave || "todo"}
                className={rango === r.clave ? "chip activo" : "chip"}
                onClick={() => setRango(r.clave)}
              >
                {r.etiqueta}
              </button>
            ))}
          </div>
        </div>

        {resumen.error && <p className="aviso error">{resumen.error}</p>}
        <FilaKpis metricas={metricasDe(resumen.datos)} />
      </section>

      <section className="tarjeta">
        <div className="tarjeta-cabecera">
          <h2>Tendencia</h2>
          <div className="filtros">
            <select value={metrica} onChange={(e) => setMetrica(e.target.value)} aria-label="Métrica">
              {METRICAS_TENDENCIA.map((m) => (
                <option key={m.api} value={m.api}>
                  {m.etiqueta}
                </option>
              ))}
            </select>
            <select
              value={intervalo}
              onChange={(e) => setIntervalo(e.target.value)}
              aria-label="Agrupación"
            >
              {INTERVALOS.map((i) => (
                <option key={i.clave} value={i.clave}>
                  {i.etiqueta}
                </option>
              ))}
            </select>
          </div>
        </div>

        {tendencia.error && <p className="aviso error">{tendencia.error}</p>}
        <GraficaLinea
          puntos={puntos}
          etiqueta={definicion?.etiqueta ?? metrica}
          formato={definicion?.esPorcentaje ? (v) => porcentaje(v, 0) : (v) => numero(v)}
        />
        {puntos.length > 0 && (
          <p className="pie-grafica">
            {tendencia.datos?.intervalo === "week" ? "Media por semana" : "Media por periodo"} ·{" "}
            {puntos.length} {puntos.length === 1 ? "periodo" : "periodos"}
          </p>
        )}
      </section>

      <section className="tarjeta">
        <h2>Por playlist</h2>
        <GraficaPlaylist datos={resumen.datos?.por_playlist ?? []} criterio="win_rate" />
        <h3 className="sub">BPM medio</h3>
        <GraficaPlaylist datos={resumen.datos?.por_playlist ?? []} criterio="avg_bpm" />
      </section>

      <section className="tarjeta">
        <h2>Ultimas partidas</h2>
        {replays.error && <p className="aviso error">{replays.error}</p>}
        <TablaPartidas partidas={replays.datos?.items ?? []} />
        {replays.datos && (
          <p className="pie-grafica">
            Mostrando {replays.datos.items.length} de {replays.datos.total}
          </p>
        )}
      </section>
    </div>
  );
}