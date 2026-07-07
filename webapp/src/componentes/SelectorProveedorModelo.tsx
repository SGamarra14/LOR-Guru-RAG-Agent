"use client";
// Selector en dos pasos: proveedor -> modelo de ese proveedor.
// La verificación es POR MODELO (dato de GET /proveedores): solo el que
// corrió el set de evaluación completo lleva la insignia — no se extiende a
// los demás modelos del mismo proveedor.
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Proveedor, ProveedorId } from "@/lib/tipos";

type Props = {
  proveedores: Proveedor[];
  proveedor: ProveedorId;
  modelo: string;
  onCambioProveedor: (p: ProveedorId) => void;
  onCambioModelo: (m: string) => void;
};

export function SelectorProveedorModelo({
  proveedores,
  proveedor,
  modelo,
  onCambioProveedor,
  onCambioModelo,
}: Props) {
  const actual = proveedores.find((p) => p.id === proveedor);

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="space-y-2">
        <Label>Proveedor</Label>
        <Select
          value={proveedor}
          onValueChange={(v) => {
            const nuevo = proveedores.find((p) => p.id === v);
            onCambioProveedor(v as ProveedorId);
            if (nuevo) onCambioModelo(nuevo.modelo_default);
          }}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Elige proveedor" />
          </SelectTrigger>
          <SelectContent>
            {proveedores.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label>Modelo</Label>
        <Select value={modelo} onValueChange={onCambioModelo}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Elige modelo" />
          </SelectTrigger>
          <SelectContent>
            {actual?.modelos.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                <span className="flex items-center gap-2">
                  {m.nombre}
                  {m.verificado && (
                    <Badge className="bg-primary/15 text-primary border-primary/40">
                      Recomendado · verificado 16/16
                    </Badge>
                  )}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {actual && (
          <p className="text-xs text-muted-foreground">
            {actual.modelos.find((m) => m.id === modelo)?.nota ||
              "Este modelo no ha corrido el set de evaluación del proyecto."}
          </p>
        )}
      </div>
    </div>
  );
}
