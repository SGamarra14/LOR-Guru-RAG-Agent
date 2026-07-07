"use client";
// El progreso del agente en tiempo real — la razón de ser del SSE por pasos:
// el usuario ve QUÉ está haciendo el agente (qué tool, con qué argumentos,
// cuántas cartas devolvió), no un spinner genérico.
import type { PasoProgreso } from "@/lib/tipos";

function Icono({ estado }: { estado: PasoProgreso["estado"] }) {
  if (estado === "en_curso")
    return (
      <span className="mt-0.5 inline-block size-3 shrink-0 animate-spin rounded-full border-2 border-accent border-t-transparent" />
    );
  if (estado === "error")
    return <span className="mt-0.5 shrink-0 text-destructive">✕</span>;
  return <span className="mt-0.5 shrink-0 text-primary">◆</span>;
}

export function ProgresoAgente({ pasos }: { pasos: PasoProgreso[] }) {
  if (pasos.length === 0) return null;
  return (
    <ol className="space-y-2 rounded-md border border-border/60 bg-card/60 p-4">
      {pasos.map((paso) => (
        <li key={paso.id} className="flex gap-2 text-sm">
          <Icono estado={paso.estado} />
          <div>
            <span className={paso.estado === "en_curso" ? "text-accent" : ""}>
              {paso.etiqueta}
            </span>
            {paso.detalle && (
              <span className="ml-2 font-mono text-xs text-muted-foreground">
                {paso.detalle}
              </span>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
