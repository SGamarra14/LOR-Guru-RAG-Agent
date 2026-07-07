// Tipos del dominio. Los shapes de la API se RE-EXPORTAN desde los tipos
// generados por openapi-typescript (src/lib/openapi.d.ts) — nunca se
// transcriben a mano, para que no se desincronicen de Pydantic.
// Regenerar tras cambios en el backend:
//   python -m scripts.exportar_openapi && npm run tipos
import type { components } from "./openapi";

export type Carta = components["schemas"]["CartaOut"];
export type RespuestaAgente = components["schemas"]["AgenteResponse"];
export type Proveedor = components["schemas"]["ProveedorOut"];
export type Modelo = components["schemas"]["ModeloOut"];
export type Llamada = components["schemas"]["LlamadaTool"];
export type ProveedorId = components["schemas"]["AgenteRequest"]["proveedor"];

// El contrato de eventos de POST /agente/stream (SSE por pasos, fase 2).
// Estos no están en el schema OpenAPI (viajan dentro del stream), así que se
// tipan aquí, espejo de lorguru/agente.py:eventos_agente.
export type EventoAgente =
  | { tipo: "inicio"; proveedor: string; modelo: string }
  | { tipo: "tool_use"; tool: string; entrada: Record<string, unknown> }
  | { tipo: "tool_result"; tool: string; total: number; error?: string | null }
  | { tipo: "error"; status: number; detalle: string }
  | {
      tipo: "respuesta";
      texto: string;
      cartas: Carta[];
      metodo_cartas: RespuestaAgente["metodo_cartas"];
      llamadas: Llamada[];
    };

// Un paso ya humanizado, listo para pintar en la línea de progreso.
export type PasoProgreso = {
  id: number;
  etiqueta: string;
  detalle?: string;
  estado: "en_curso" | "hecho" | "error";
};
