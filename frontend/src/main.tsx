import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import "./estilos.css";

const contenedor = document.getElementById("root");
if (!contenedor) throw new Error("Falta #root en index.html");

createRoot(contenedor).render(
  <StrictMode>
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <App />
    </BrowserRouter>
  </StrictMode>,
);