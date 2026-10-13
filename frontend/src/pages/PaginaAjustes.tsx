import { useState, useEffect } from "react";

import {
  useSesion,
  useEstadoToken,
  useEstadoSync,
  useCuentas,
} from "../hooks/useApi";
import { api, ErrorApi, type GameAccount } from "../lib/api";
import { haceCuanto } from "../lib/format";

export function PaginaAjustes() {
  const sesion = useSesion();
  const token = useEstadoToken();
  const sync = useEstadoSync();
  const cuentas = useCuentas();

  const [nuevoToken, setNuevoToken] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const [plataforma, setPlataforma] = useState("steam");
  const [identificador, setIdentificador] = useState("");
  const [nombre, setNombre] = useState("");

  // --- obtener SteamID64 desde nombre vanity ---
  const [obteniendoSteamId, setObteniendoSteamId] = useState(false);
  const [vanityInput, setVanityInput] = useState("");
  const [steamIdEncontrado, setSteamIdEncontrado] = useState<string | null>(null);

  // --- Forzar recarga completa al montar ---
  useEffect(() => {
    token.recargar();
    cuentas.recargar();
    sync.recargar();
  }, []);

  // Sincronizar identificador con la cuenta Steam guardada
  useEffect(() => {
    if (!cuentas.cargando && cuentas.datos) {
      const cuentaSteam = cuentas.datos.find((c) => c.platform === "steam");
      if (cuentaSteam) {
        setIdentificador(cuentaSteam.platform_id);
        setNombre(cuentaSteam.display_name ?? "");
      }
    }
  }, [cuentas.datos]);

  async function obtenerSteamId64() {
    if (!vanityInput.trim()) return;
    setObteniendoSteamId(true);
    setSteamIdEncontrado(null);
    try {
      const resp = await fetch(
        `${import.meta.env.VITE_API_URL}/steam/resolve-vanity?vanity=${encodeURIComponent(vanityInput.trim())}`
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err?.error?.message ?? "No se pudo resolver el nombre");
      }
      const data = await resp.json();
      setSteamIdEncontrado(data.steamId);
      setIdentificador(data.steamId);
    } catch (e) {
      setAviso(e instanceof Error ? e.message : "No se pudo obtener el SteamID64");
    } finally {
      setObteniendoSteamId(false);
    }
  }

  async function guardarToken(evento: React.FormEvent) {
    evento.preventDefault();
    setOcupado(true);
    setAviso(null);
    try {
      await api.guardarToken(nuevoToken);
      setNuevoToken("");
      token.recargar();
      setAviso("Token guardado y validado contra Ballchasing.");
    } catch (e) {
      setAviso(e instanceof ErrorApi ? e.message : "No se ha podido guardar el token.");
    } finally {
      setOcupado(false);
    }
  }

  async function anadirCuenta(evento: React.FormEvent) {
    evento.preventDefault();
    setOcupado(true);
    setAviso(null);
    try {
      await api.crearCuenta({
        platform: plataforma,
        platform_id: identificador,
        display_name: nombre || null,
      });
      setIdentificador("");
      setNombre("");
      cuentas.recargar();
      setAviso("Cuenta de juego añadida.");
    } catch (e) {
      setAviso(e instanceof ErrorApi ? e.message : "No se ha podido añadir la cuenta.");
    } finally {
      setOcupado(false);
    }
  }

  const conCredencial = token.datos?.configured === true;

  return (
    <div className="pagina">
      <section className="tarjeta">
        <h2>Token de Ballchasing</h2>
        <p className="nota">
          Ballchasing limita cada token por separado, asi que la cuota de una cuenta es
          solo tuya. Se guarda cifrado y nunca se devuelve por la API.
        </p>

        <p className={conCredencial ? "estado ok" : "estado pendiente"}>
          {conCredencial
            ? `Configurado${token.datos?.validated ? " y validado" : ""} · comprobado ${haceCuanto(token.datos?.last_validated_at ?? null)}`
            : "Sin token: todavía no se puede sincronizar nada."}
        </p>

        <form onSubmit={guardarToken}>
          <label htmlFor="token">Token de Ballchasing</label>
          <input
            id="token"
            type="password"
            autoComplete="off"
            placeholder={conCredencial ? "Pega aqui el token nuevo para sustituirlo" : "pega tu token de ballchasing.com"}
            value={nuevoToken}
            onChange={(e) => setNuevoToken(e.target.value)}
            required
          />
          <button type="submit" disabled={ocupado}>
            Guardar token
          </button>
          {conCredencial && (
            <button
              type="button"
              className="secundario peligro"
              disabled={ocupado}
              onClick={() => api.borrarToken().then(() => { token.recargar(); setAviso("Token borrado."); })}
            >
              Borrar token
            </button>
          )}
        </form>
        <p className="nota">
          Lo tienes en <span className="mono">ballchasing.com → Settings → API Access</span>.
        </p>
      </section>

      <section className="tarjeta">
        <h2>Cuentas de juego</h2>
        <p className="nota">
          Con la cuenta de juego es como se sabe que replays son tuyos, aunque los subiera
          otra persona.
        </p>

        <ul className="lista-cuentas">
          {(cuentas.datos ?? []).map((c: GameAccount) => (
            <li key={c.id}>
              <span className="mono">
                {c.platform}:{c.platform_id}
              </span>
              {c.display_name && <span className="apodo"> · {c.display_name}</span>}
              <button
                className="secundario peligro"
                disabled={ocupado}
                onClick={() => api.borrarCuenta(c.id).then(() => cuentas.recargar())}
                aria-label={`Borrar ${c.platform} ${c.platform_id}`}
              >
                Borrar
              </button>
            </li>
          ))}
          {(cuentas.datos ?? []).length === 0 && <li className="nota">Ninguna todavia.</li>}
        </ul>

        <form onSubmit={anadirCuenta}>
          <label htmlFor="plataforma">Plataforma</label>
          <select id="plataforma" value={plataforma} onChange={(e) => setPlataforma(e.target.value)}>
            <option value="steam">Steam</option>
            <option value="epic">Epic</option>
            <option value="ps4">PlayStation</option>
            <option value="switch">Switch</option>
            <option value="xbox">Xbox</option>
          </select>

          <label htmlFor="identificador">Identificador</label>
          <div className="campo-con-ayuda">
            <input
              id="identificador"
              value={identificador}
              onChange={(e) => setIdentificador(e.target.value)}
              placeholder="76561199000000001"
              required
            />
            {plataforma === "steam" && (
              <div className="ayuda-steam">
                <label htmlFor="vanity">
                  <input
                    id="vanity"
                    type="text"
                    value={vanityInput}
                    onChange={(e) => setVanityInput(e.target.value)}
                    placeholder="Tu nombre en Steam (ej: Snakeyesmp)"
                    aria-label="Tu nombre en Steam (ej: Snakeyesmp)"
                  />
                </label>
                <button
                  type="button"
                  className="secundario"
                  disabled={obteniendoSteamId || !vanityInput.trim()}
                  onClick={obtenerSteamId64}
                >
                  {obteniendoSteamId ? "Obteniendo…" : "Obtener mi SteamID64"}
                </button>
                {steamIdEncontrado && (
                  <p className="exito">
                    ¡Encontrado! SteamID64: <strong>{steamIdEncontrado}</strong>
                    <button
                      type="button"
                      className="secundario pequeño"
                      onClick={() => { setIdentificador(steamIdEncontrado); setSteamIdEncontrado(null); }}
                    >
                      Usar este
                    </button>
                  </p>
                )}
              </div>
            )}
          </div>

          <label htmlFor="nombre">Nombre en el juego (opcional)</label>
          <input id="nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} />

          <button type="submit" disabled={ocupado}>
            Añadir cuenta
          </button>
        </form>
      </section>

      <section className="tarjeta">
        <h2>Sincronizacion</h2>
        <p className="estado">
          {sync.datos?.total_replays ?? 0} partidas · ultima sincronizacion{" "}
          {haceCuanto(sync.datos?.last_synced_at ?? null)}
          {sync.datos?.ultimo_estado && ` · ultimo trabajo: ${sync.datos.ultimo_estado}`}
        </p>
        {sync.datos?.ultimo_error && <p className="aviso error">{sync.datos.ultimo_error}</p>}

        <div className="acciones">
          <button
            disabled={!conCredencial || ocupado}
            onClick={() =>
              api.encolarSync().then(() => {
                sync.recargar();
                setAviso("Sincronizacion encolada.");
              })
            }
          >
            Sincronizar ahora
          </button>
          <label className="interruptor">
            <input
              type="checkbox"
              checked={sync.datos?.auto_sync ?? false}
              onChange={(e) => api.ajustesSync(e.target.checked).then(() => sync.recargar())}
            />
            Sincronizar automaticamente
          </label>
        </div>

        {!conCredencial && (
          <p className="aviso">Anade antes un token de Ballchasing para poder sincronizar.</p>
        )}
      </section>

      <section className="tarjeta">
        <h2>Cuenta</h2>
        <p className="nota">
          Sesion iniciada como <span className="mono">{sesion.usuario?.email}</span>.
        </p>
        <p className="nota">
          Al borrar tu cuenta se van tambien tus estadisticas y las partidas que no
          compartas con nadie mas.
        </p>
        <button className="secundario" onClick={() => sesion.salir()}>
          Cerrar sesion
        </button>
      </section>

      {aviso && <p className="aviso">{aviso}</p>}
    </div>
  );
}