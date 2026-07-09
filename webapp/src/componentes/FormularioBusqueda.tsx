"use client";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CampoApiKey } from "@/componentes/CampoApiKey";
import { SelectorProveedorModelo } from "@/componentes/SelectorProveedorModelo";
import type { ParametrosBusqueda } from "@/hooks/useAgenteStream";
import type { Proveedor, ProveedorId } from "@/lib/tipos";

const EJEMPLOS = [
  "Hechizos baratos que hagan daño al nexo enemigo",
  "Unidades de Jonia con Evasión para un mazo agresivo",
  "Cartas que revivan aliados que ya murieron",
];

type Props = {
  proveedores: Proveedor[];
  buscando: boolean;
  onBuscar: (params: ParametrosBusqueda) => void;
  onCancelar: () => void;
};

export function FormularioBusqueda({
  proveedores,
  buscando,
  onBuscar,
  onCancelar,
}: Props) {
  const [consulta, setConsulta] = useState("");
  const [proveedor, setProveedor] = useState<ProveedorId>("anthropic");
  const [modelo, setModelo] = useState("claude-sonnet-5");
  const [apiKey, setApiKey] = useState("");
  // El acordeón arranca abierto (hay que configurar la clave) y se colapsa
  // solo al lanzar la primera búsqueda — despeja la pantalla una vez
  // configurado, sin esconder nada antes de tiempo.
  const [configAbierta, setConfigAbierta] = useState(true);

  const listo = consulta.trim().length > 0 && apiKey.trim().length >= 8;

  const nombreProveedor =
    proveedores.find((p) => p.id === proveedor)?.nombre ?? proveedor;
  const nombreModelo =
    proveedores
      .find((p) => p.id === proveedor)
      ?.modelos.find((m) => m.id === modelo)?.nombre ?? modelo;
  const resumenConfig = `${nombreProveedor} · ${nombreModelo} · ${
    apiKey ? "clave lista" : "falta la clave"
  }`;

  const lanzar = () => {
    if (!listo || buscando) return;
    setConfigAbierta(false);
    onBuscar({ consulta: consulta.trim(), proveedor, modelo, apiKey });
  };

  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        lanzar();
      }}
    >
      <div className="space-y-2">
        <Label htmlFor="consulta">¿Qué cartas buscas?</Label>
        <Textarea
          id="consulta"
          rows={2}
          placeholder="Descríbelas en español, como se lo dirías a otra persona…"
          value={consulta}
          onChange={(e) => setConsulta(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              lanzar();
            }
          }}
        />
        <div className="flex flex-wrap gap-2">
          {EJEMPLOS.map((ej) => (
            <button
              key={ej}
              type="button"
              onClick={() => setConsulta(ej)}
              className="rounded-full border border-border/60 px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-accent hover:text-accent"
            >
              {ej}
            </button>
          ))}
        </div>
      </div>

      <details
        open={configAbierta}
        onToggle={(e) => setConfigAbierta(e.currentTarget.open)}
        className="group rounded-md border border-border/60 bg-background/30"
      >
        <summary className="flex cursor-pointer select-none list-none items-center justify-between gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
          <span className="font-display text-sm font-semibold tracking-wide text-primary">
            Configuración del Agente
          </span>
          <span className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="hidden sm:inline">{resumenConfig}</span>
            <span
              aria-hidden
              className="text-accent transition-transform group-open:rotate-180"
            >
              ▾
            </span>
          </span>
        </summary>
        <div className="space-y-5 border-t border-border/60 p-4">
          <SelectorProveedorModelo
            proveedores={proveedores}
            proveedor={proveedor}
            modelo={modelo}
            onCambioProveedor={setProveedor}
            onCambioModelo={setModelo}
          />
          <CampoApiKey proveedor={proveedor} valor={apiKey} onCambio={setApiKey} />
        </div>
      </details>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!listo || buscando} className="px-8">
          {buscando ? "Consultando al agente…" : "Buscar cartas"}
        </Button>
        {buscando && (
          <Button type="button" variant="outline" onClick={onCancelar}>
            Cancelar
          </Button>
        )}
      </div>
    </form>
  );
}
