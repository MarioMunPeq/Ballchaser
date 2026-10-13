/**
 * Tests de lo que mas falla en pantalla: formatear numeros, fechas y series.
 *
 * No se testean componentes a proposito: los hooks y el DOM los cubre el navegador, y
 * con recursos limitados rinde mas comprobar la logica pura.
 */

import { describe, expect, it } from "vitest";

import { aPuntos, escalaEje, fechaCorta, haceCuanto, numero, porcentaje, resultado, segundos } from "../lib/format";

describe("numero", () => {
  it("muestra un guion cuando no hay dato", () => {
    expect(numero(null)).toBe("—");
    expect(numero(undefined)).toBe("—");
    expect(numero(Number.NaN)).toBe("—");
  });

  it("muestra decimales cuando se piden", () => {
    expect(numero(1234)).toBe("1.234");
    expect(numero(66.67, 1)).toBe("66,7");
  });

  it("no rompe con el cero", () => {
    expect(numero(0)).toBe("0");
  });
});

describe("porcentaje", () => {
  it("anade el signo de porcentaje", () => {
    expect(porcentaje(50, 0)).toBe("50 %");
  });

  it("deja el guion si falta", () => {
    expect(porcentaje(null)).toBe("—");
  });
});

describe("segundos", () => {
  it("pasa a minutos y segundos con dos digitos", () => {
    expect(segundos(347)).toBe("5:47");
    expect(segundos(65)).toBe("1:05");
  });
});

describe("fechas", () => {
  it("acepta una fecha ISO con Z", () => {
    expect(fechaCorta("2026-03-15T20:50:00Z")).toMatch(/mar/);
  });

  it("no rompe con una fecha basura", () => {
    expect(fechaCorta("no-es-fecha")).toBe("—");
  });

  it("dice nunca cuando no hay fecha", () => {
    expect(haceCuanto(null)).toBe("nunca");
  });

  it("dice ahora mismo cuando acaba de pasar", () => {
    expect(haceCuanto(new Date().toISOString())).toBe("ahora mismo");
  });
});

describe("resultado", () => {
  it("traduce a castellano", () => {
    expect(resultado("win")).toBe("Victoria");
    expect(resultado("loss")).toBe("Derrota");
    expect(resultado("tie")).toBe("Empate");
  });
});

describe("aPuntos", () => {
  const puntos = [
    { periodo: "2026-03-01", valor: 520, total: 520, replays: 1 },
    { periodo: "2026-02-01", valor: null, total: null, replays: 0 },
    { periodo: "2026-01-01", valor: 610, total: 610, replays: 1 },
  ];

  it("descarta los periodos sin valor en vez de ponerlos a cero", () => {
    const serie = aPuntos(puntos);
    expect(serie).toHaveLength(2);
    expect(serie.every((p) => p.y > 0)).toBe(true);
  });

  it("ordena de mas antiguo a mas reciente", () => {
    const serie = aPuntos(puntos);
    expect(serie[0]?.etiqueta).toBe("1 ene");
    expect(serie[1]?.etiqueta).toBe("1 mar");
  });

  it("aguanta una serie vacia", () => {
    expect(aPuntos([])).toEqual([]);
  });
});

describe("escalaEje", () => {
  it("redondea el eje hacia fuera", () => {
    const { min, max } = escalaEje(3, 7);
    expect(min).toBeLessThanOrEqual(3);
    expect(max).toBeGreaterThanOrEqual(7);
  });

  it("resuelve el caso de un solo valor", () => {
    const { min, max } = escalaEje(5, 5);
    expect(min).toBeLessThan(5);
    expect(max).toBeGreaterThan(5);
  });

  it("no revienta con todos ceros", () => {
    const { min, max } = escalaEje(0, 0);
    expect(Number.isFinite(min)).toBe(true);
    expect(Number.isFinite(max)).toBe(true);
  });
});