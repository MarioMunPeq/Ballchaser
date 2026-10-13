/** Estado de autenticacion y de los datos del usuario. */

import {
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  type User,
} from "firebase/auth";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  conectarConFirebase,
  type GameAccount,
  type ReplayPaginado,
  type ResumenStats,
  type SyncEstado,
  type TendenciaRespuesta,
  type TokenEstado,
  type UserProfile,
} from "../lib/api";
import { firebaseAuth } from "../lib/firebase";

export interface Sesion {
  usuario: User | null;
  cargando: boolean;
  entrarConCorreo: (correo: string, clave: string) => Promise<void>;
  entrarConGoogle: () => Promise<void>;
  salir: () => Promise<void>;
}

/** El token que manda la API se toma siempre del usuario autenticado. */
export function useSesion(): Sesion {
  const [usuario, setUsuario] = useState<User | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    conectarConFirebase(async () => usuario?.getIdToken() ?? null);
  }, [usuario]);

  useEffect(() => {
    return onAuthStateChanged(firebaseAuth, (u) => {
      setUsuario(u);
      setCargando(false);
    });
  }, []);

  const entrarConCorreo = useCallback(async (correo: string, clave: string) => {
    await signInWithEmailAndPassword(firebaseAuth, correo, clave);
  }, []);

  const entrarConGoogle = useCallback(async () => {
    await signInWithPopup(firebaseAuth, new GoogleAuthProvider());
  }, []);

  const salir = useCallback(async () => {
    await signOut(firebaseAuth);
  }, []);

  return useMemo(
    () => ({ usuario, cargando, entrarConCorreo, entrarConGoogle, salir }),
    [usuario, cargando, entrarConCorreo, entrarConGoogle, salir],
  );
}

export interface EstadoCarga<T> {
  datos: T | null;
  cargando: boolean;
  error: string | null;
  recargar: () => void;
}

/** Hook mínimo para pedir datos y volver a pedirlos a mano. */
export function useDatos<T>(pedir: () => Promise<T>, deps: unknown[]): EstadoCarga<T> {
  const [datos, setDatos] = useState<T | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [contador, setContador] = useState(0);

  // Ejecutar petición inicial y cuando cambien las deps
  useEffect(() => {
    let vivo = true;
    setCargando(true);
    setError(null);

    const ejecutar = async () => {
      try {
        const r = await pedir();
        if (vivo) setDatos(r);
      } catch (e) {
        if (vivo) setError(e instanceof Error ? e.message : "Error");
      } finally {
        if (vivo) setCargando(false);
      }
    };

    ejecutar();

    return () => {
      vivo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, contador]);

  // Función para forzar recarga manual
  const recargar = useCallback(() => {
    setContador((c) => c + 1);
  }, []);

  return { datos, cargando, error, recargar };
}

export const usePerfil = () => useDatos<UserProfile>(() => api.perfil(), []);
export const useResumen = (playlist?: string) =>
  useDatos<ResumenStats>(() => api.resumen({ playlist }), [playlist]);
export const useEstadoSync = () => useDatos<SyncEstado>(() => api.estadoSync(), []);
export const useEstadoToken = () => useDatos<TokenEstado>(() => api.estadoToken(), []);
export const useCuentas = () => useDatos<GameAccount[]>(() => api.cuentas(), []);

export function useReplays(filtros: Record<string, string | number | undefined>) {
  const clave = JSON.stringify(filtros);
  return useDatos<ReplayPaginado>(() => api.listarReplays(JSON.parse(clave) as Record<string, string | number | undefined>), [clave]);
}

export function useTendencia(metrica: string, interval: string, playlist?: string) {
  return useDatos<TendenciaRespuesta>(
    () => api.tendencias({ metric: metrica, interval, playlist }),
    [metrica, interval, playlist],
  );
}

export type { ReplayResumen } from "../lib/api";