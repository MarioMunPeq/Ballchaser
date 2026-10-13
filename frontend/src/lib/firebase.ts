/**
 * Configuracion de Firebase Authentication.
 *
 * Los valores vienen del entorno en tiempo de compilacion (Vite). Son publicos por
 * diseño: identifican el proyecto, pero no dan acceso a el. Lo que protege de verdad es
 * que la API verifique el ID token en el servidor; ver ADR 0001.
 */

import { getApp, getApps, initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const faltaConfig = (): string[] =>
  Object.entries(config)
    .filter(([, valor]) => !valor)
    .map(([clave]) => clave);

export const firebaseConfig = config;

/** Si falta la configuracion, el app arranca pero avisa antes de romperse al login. */
export const errorDeConfiguracion: string | null = faltaConfig().length
  ? `Falta configurar en .env.local: ${faltaConfig().join(", ")}`
  : null;

export const firebaseApp = getApps().length ? getApp() : initializeApp(config);
export const firebaseAuth = getAuth(firebaseApp);

export const URL_API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";