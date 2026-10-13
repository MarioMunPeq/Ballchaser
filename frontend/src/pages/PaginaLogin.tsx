import { useState, type FormEvent } from "react";

import { useSesion } from "../hooks/useApi";
import { errorDeConfiguracion } from "../lib/firebase";

export function PaginaLogin() {
  const sesion = useSesion();
  const [correo, setCorreo] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setOcupado(true);
    setError(null);
    try {
      await sesion.entrarConCorreo(correo, clave);
    } catch (e) {
      // Los errores de Firebase vienen en ingles y sin traduccion util: se reconoce el
      // codigo cuando se puede y se cae a un texto generico si no.
      const codigo = (e as { code?: string }).code ?? "";
      setError(
        {
          "auth/invalid-credential": "Correo o contrasena incorrectos.",
          "auth/too-many-requests": "Demasiados intentos. Espera un momento.",
          "auth/invalid-email": "Ese correo no tiene buena pinta.",
        }[codigo] ?? "No se ha podido iniciar sesion. Intentalo otra vez.",
      );
    } finally {
      setOcupado(false);
    }
  }

  return (
    <main className="centro">
      <div className="caja login">
        <h1 className="marca">BallChaser</h1>
        <p className="subtitulo">Tus replays de Rocket League, en graficas.</p>

        {errorDeConfiguracion && (
          <p className="aviso error">
            <strong>Falta la configuracion de Firebase.</strong>
            <br />
            {errorDeConfiguracion}
          </p>
        )}

        <form onSubmit={enviar}>
          <label htmlFor="correo">Correo</label>
          <input
            id="correo"
            type="email"
            autoComplete="email"
            value={correo}
            onChange={(e) => setCorreo(e.target.value)}
            required
          />

          <label htmlFor="clave">Contrasena</label>
          <input
            id="clave"
            type="password"
            autoComplete="current-password"
            value={clave}
            onChange={(e) => setClave(e.target.value)}
            required
          />

          {error && <p className="aviso error">{error}</p>}

          <button type="submit" disabled={ocupado || Boolean(errorDeConfiguracion)}>
            {ocupado ? "Entrando…" : "Entrar"}
          </button>
        </form>

        <div className="separador">
          <span>o</span>
        </div>

        <button
          type="button"
          className="secundario"
          onClick={() => sesion.entrarConGoogle().catch(() => setError("No se ha podido abrir Google."))}
          disabled={Boolean(errorDeConfiguracion)}
        >
          Continuar con Google
        </button>

        <p className="nota">
          El login lo hace Firebase. Esta aplicacion solo recibe un token que ya viene
          firmado: nunca ve tu contrasena.
        </p>
      </div>
    </main>
  );
}