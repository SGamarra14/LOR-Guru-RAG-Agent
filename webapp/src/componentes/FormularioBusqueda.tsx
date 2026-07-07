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

  const listo = consulta.trim().length > 0 && apiKey.trim().length >= 8;

  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (listo && !buscando)
          onBuscar({ consulta: consulta.trim(), proveedor, modelo, apiKey });
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
              if (listo && !buscando)
                onBuscar({ consulta: consulta.trim(), proveedor, modelo, apiKey });
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

      <SelectorProveedorModelo
        proveedores={proveedores}
        proveedor={proveedor}
        modelo={modelo}
        onCambioProveedor={setProveedor}
        onCambioModelo={setModelo}
      />

      <CampoApiKey proveedor={proveedor} valor={apiKey} onCambio={setApiKey} />

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
