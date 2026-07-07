"use client";
// La API key es un SECRETO del usuario (BYOK):
// - input type="password" (nunca visible por defecto),
// - vive solo en memoria (estado React) mientras dura la pestaña,
// - persistirla en localStorage es una decisión EXPLÍCITA del usuario (el
//   checkbox de abajo), nunca automática ni silenciosa,
// - jamás se manda a logs ni analítica; solo viaja en el body del POST.
import { useEffect, useState } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ProveedorId } from "@/lib/tipos";

const CLAVE_STORAGE = (proveedor: string) => `lorguru_api_key_${proveedor}`;

type Props = {
  proveedor: ProveedorId;
  valor: string;
  onCambio: (valor: string) => void;
};

export function CampoApiKey({ proveedor, valor, onCambio }: Props) {
  const [recordar, setRecordar] = useState(false);
  const [mostrar, setMostrar] = useState(false);

  // Al cambiar de proveedor, recuperar la clave SOLO si el usuario optó por
  // recordarla antes para ese proveedor.
  useEffect(() => {
    const guardada = localStorage.getItem(CLAVE_STORAGE(proveedor));
    setRecordar(guardada !== null);
    onCambio(guardada ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proveedor]);

  const cambiar = (nuevo: string) => {
    onCambio(nuevo);
    if (recordar) localStorage.setItem(CLAVE_STORAGE(proveedor), nuevo);
  };

  const cambiarRecordar = (activo: boolean) => {
    setRecordar(activo);
    if (activo && valor) localStorage.setItem(CLAVE_STORAGE(proveedor), valor);
    if (!activo) localStorage.removeItem(CLAVE_STORAGE(proveedor));
  };

  return (
    <div className="space-y-2">
      <Label htmlFor="api-key">Tu API key del proveedor</Label>
      <div className="flex gap-2">
        <Input
          id="api-key"
          type={mostrar ? "text" : "password"}
          autoComplete="off"
          spellCheck={false}
          placeholder="Se usa solo para esta búsqueda; no se guarda en el servidor"
          value={valor}
          onChange={(e) => cambiar(e.target.value)}
        />
        <button
          type="button"
          onClick={() => setMostrar((m) => !m)}
          className="shrink-0 rounded-md border border-input px-3 text-xs text-muted-foreground hover:text-foreground"
          aria-label={mostrar ? "Ocultar clave" : "Mostrar clave"}
        >
          {mostrar ? "Ocultar" : "Ver"}
        </button>
      </div>
      <label className="flex items-center gap-2 text-xs text-muted-foreground">
        <input
          type="checkbox"
          checked={recordar}
          onChange={(e) => cambiarRecordar(e.target.checked)}
          className="accent-primary"
        />
        Recordar esta clave en este navegador (localStorage). Si la pestaña es
        compartida o pública, déjalo apagado.
      </label>
    </div>
  );
}
