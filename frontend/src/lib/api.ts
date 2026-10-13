/**
 * Cliente HTTP de la API.
 *
 * La peticion solo lleva el ID token de Firebase; de quien es el usuario lo decide el
 * servidor a partir de ese token, nunca el cuerpo de la peticion (ver ADR 0001).
 */

import { URL_API } from "./firebase";

export class ErrorApi extends Error {
  constructor(
    readonly status: number,
    readonly codigo: string,
    mensaje: string,
  ) {
    super(mensaje);
    this.name = "ErrorApi";
  }
}

type Token = () => Promise<string | null>;

let obtenerToken: Token = async () => null;

export function conectarConFirebase(accion: Token): void {
  obtenerToken = accion;
}

async function pedir<T>(ruta: string, init: RequestInit = {}): Promise<T> {
  const token = await obtenerToken();
  if (!token) {
    throw new ErrorApi(401, "no_login", "Has cerrado sesion.");
  }

  const respuesta = await fetch(`${URL_API}${ruta}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
  });

  if (respuesta.status === 204) {
    return undefined as T;
  }

  const cuerpo = await respuesta.json().catch(() => null);

  if (!respuesta.ok) {
    const error = cuerpo as { error?: { code?: string; message?: string } } | null;
    throw new ErrorApi(
      respuesta.status,
      error?.error?.code ?? "desconocido",
      error?.error?.message ?? `Error ${respuesta.status}`,
    );
  }

  return cuerpo as T;
}

// --- tipos de la API (ver backend/app/schemas) ---

export interface UserProfile {
  id: string;
  email: string | null;
  display_name: string | null;
  created_at: string;
}

export interface ReplayResumen {
  id: string;
  played_at: string;
  playlist_id: string;
  playlist_name: string | null;
  map_code: string | null;
  map_name: string | null;
  blue_goals: number | null;
  orange_goals: number | null;
  team: string;
  result: "win" | "loss" | "tie";
  score: number | null;
  goals: number | null;
  assists: number | null;
  saves: number | null;
  bpm: number | null;
  centers: number | null;
}

export interface ReplayPaginado {
  items: ReplayResumen[];
  total: number;
  limit: number;
  offset: number;
}

export interface StatsPorPlaylist {
  playlist_id: string;
  playlist_name: string | null;
  replays: number;
  wins: number;
  win_rate: number | null;
  avg_score: number | null;
  avg_bpm: number | null;
}

export interface ResumenStats {
  replays: number;
  wins: number;
  losses: number;
  ties: number;
  win_rate: number | null;
  goals: number;
  goals_against: number;
  assists: number;
  saves: number;
  shots: number;
  demos_inflicted: number;
  demos_taken: number;
  avg_score: number | null;
  avg_bpm: number | null;
  avg_percent_full_boost: number | null;
  avg_percent_zero_boost: number | null;
  avg_percent_supersonic_speed: number | null;
  avg_percent_ground: number | null;
  avg_duration: number | null;
  por_playlist: StatsPorPlaylist[];
}

export interface PuntoTendencia {
  periodo: string;
  valor: number | null;
  total: number | null;
  replays: number;
}

export interface TendenciaRespuesta {
  metrica: string;
  intervalo: string;
  puntos: PuntoTendencia[];
}

export interface TokenEstado {
  configured: boolean;
  validated: boolean;
  last_validated_at: string | null;
}

export interface GameAccount {
  id: string;
  platform: string;
  platform_id: string;
  display_name: string | null;
  created_at: string;
}

export interface SyncEstado {
  encolado: boolean;
  ultimo_job_id: string | null;
  ultimo_estado: string | null;
  ultimo_error: string | null;
  replays_nuevos: number;
  replays_omitidos: number;
  last_synced_at: string | null;
  last_replay_date: string | null;
  total_replays: number;
  auto_sync: boolean;
  intentos: number;
  proximo_intento: string | null;
}

// --- llamadas ---

export const api = {
  perfil: () => pedir<UserProfile>("/me"),

  listarReplays: (params: Record<string, string | number | undefined>) =>
    pedir<ReplayPaginado>(`/replays?${new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)]),
    )}`),

  resumen: (params: Record<string, string | undefined>) =>
    pedir<ResumenStats>(`/stats/summary?${new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "") as [string, string][],
    )}`),

  tendencias: (params: Record<string, string | undefined>) =>
    pedir<TendenciaRespuesta>(`/stats/trends?${new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "") as [string, string][],
    )}`),

  estadoToken: () => pedir<TokenEstado>("/me/ballchasing-token"),

  guardarToken: (token: string) =>
    pedir<TokenEstado>("/me/ballchasing-token", {
      method: "PUT",
      body: JSON.stringify({ token }),
    }),

  borrarToken: () => pedir<void>("/me/ballchasing-token", { method: "DELETE" }),

  cuentas: () => pedir<GameAccount[]>("/me/game-accounts"),

  crearCuenta: (datos: { platform: string; platform_id: string; display_name?: string | null }) =>
    pedir<GameAccount>("/me/game-accounts", { method: "POST", body: JSON.stringify(datos) }),

  borrarCuenta: (id: string) => pedir<void>(`/me/game-accounts/${id}`, { method: "DELETE" }),

  encolarSync: () =>
    pedir<{ job_id: string; status: string; ya_estaba_encolada: boolean }>("/sync", {
      method: "POST",
    }),

  estadoSync: () => pedir<SyncEstado>("/sync/status"),

  ajustesSync: (autoSync: boolean) =>
    pedir<SyncEstado>("/me/sync-settings", {
      method: "PATCH",
      body: JSON.stringify({ auto_sync: autoSync }),
    }),
};