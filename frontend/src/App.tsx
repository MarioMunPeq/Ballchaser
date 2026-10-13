import { Link, NavLink, Navigate, Outlet, Route, Routes } from "react-router-dom";

import { useSesion } from "./hooks/useApi";
import { PaginaAjustes } from "./pages/PaginaAjustes";
import { PaginaLogin } from "./pages/PaginaLogin";
import { PaginaPanel } from "./pages/PaginaPanel";

function Cargando() {
  return (
    <main className="centro">
      <p className="vacio">Cargando…</p>
    </main>
  );
}

function ConSesion() {
  const sesion = useSesion();
  if (sesion.cargando) return <Cargando />;
  return sesion.usuario ? <Outlet /> : <Navigate to="/entrar" replace />;
}

function SinSesion() {
  const sesion = useSesion();
  if (sesion.cargando) return <Cargando />;
  return sesion.usuario ? <Navigate to="/" replace /> : <Outlet />;
}

function Marco() {
  const sesion = useSesion();

  return (
    <>
      <header className="cabecera">
        <Link to="/" className="marca">
          BallChaser
        </Link>
        <nav>
          <NavLink to="/" end>
            Panel
          </NavLink>
          <NavLink to="/ajustes">Ajustes</NavLink>
        </nav>
        <button className="secundario perfil" onClick={() => sesion.salir()}>
          {sesion.usuario?.displayName ?? sesion.usuario?.email ?? "Salir"}
        </button>
      </header>
      <Outlet />
    </>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<SinSesion />}>
        <Route path="/entrar" element={<PaginaLogin />} />
      </Route>

      <Route element={<ConSesion />}>
        <Route element={<Marco />}>
          <Route index element={<PaginaPanel />} />
          <Route path="ajustes" element={<PaginaAjustes />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

