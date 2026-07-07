"use client";
// El panel de "por qué estas cartas": colapsable y no intrusivo. Muestra las
// tool calls que hizo el agente (con sus argumentos) y cómo se determinaron
// las cartas de la respuesta (metodo_cartas) — conecta con la idea original
// del proyecto: no solo QUÉ encontró, sino CÓMO.
import { useState } from "react";

import type { Llamada, RespuestaAgente } from "@/lib/tipos";

const EXPLICACION_METODO: Record<RespuestaAgente["metodo_cartas"], string> = {
  citadas:
    "El agente citó explícitamente estas cartas en su respuesta final (línea CARTAS:).",
  ultima_llamada:
    "El agente no citó cartas explícitamente; se muestran las de su última búsqueda con resultados.",
  ninguna: "El agente no encontró cartas para esta consulta.",
};

export function PanelTransparencia({
  llamadas,
  metodo,
}: {
  llamadas: Llamada[];
  metodo: RespuestaAgente["metodo_cartas"];
}) {
  const [abierto, setAbierto] = useState(false);

  return (
    <div className="rounded-md border border-border/60 bg-card/40">
      <button
        type="button"
        onClick={() => setAbierto((a) => !a)}
        className="flex w-full items-center justify-between px-4 py-2 text-sm text-muted-foreground transition-colors hover:text-accent"
        aria-expanded={abierto}
      >
        <span>¿Cómo encontró el agente estas cartas?</span>
        <span aria-hidden>{abierto ? "▲" : "▼"}</span>
      </button>
      {abierto && (
        <div className="space-y-3 border-t border-border/60 px-4 py-3 text-sm">
          <p className="text-muted-foreground">{EXPLICACION_METODO[metodo]}</p>
          <ol className="space-y-2">
            {llamadas.map((llamada, i) => (
              <li key={i} className="font-mono text-xs">
                <span className="text-accent">{i + 1}.</span>{" "}
                <span className="text-primary">{llamada.tool}</span>(
                {JSON.stringify(llamada.entrada)}) →{" "}
                {llamada.total} cartas
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
