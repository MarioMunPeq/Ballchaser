/** Fila de KPIs: los numeros grandes de arriba del panel. */

import type { MetricaKpi } from "../lib/metricas";

export function FilaKpis({ metricas }: { metricas: MetricaKpi[] }) {
  if (metricas.length === 0) {
    return (
      <div className="kpis kpis-vacias" aria-hidden="true">
        {Array.from({ length: 6 }, (_, i) => (
          <div className="kpi" key={i}>
            <span className="kpi-etiqueta">—</span>
            <span className="kpi-valor">· · ·</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="kpis">
      {metricas.map((m) => (
        <div className="kpi" key={m.clave}>
          <span className="kpi-etiqueta">{m.etiqueta}</span>
          <span className="kpi-valor">{m.valor}</span>
          {m.detalle && <span className="kpi-detalle">{m.detalle}</span>}
        </div>
      ))}
    </div>
  );
}