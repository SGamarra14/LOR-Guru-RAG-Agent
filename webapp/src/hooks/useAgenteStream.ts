"use client";
// El consumidor del SSE por pasos de POST /agente/stream.
//
// Decisión de la fase 3 (GUIA_FASE3.md §2): consumidor PROPIO en vez de un
// adaptador al protocolo de useChat del Vercel AI SDK. Los eventos del
// backend son pasos estructurados de un agente (tool_use/tool_result) que
// terminan en UN payload final con cartas — no un chat de tokens. Meterlos
// en el modelo de mensajes de useChat exigiría un route handler traductor y
// data-parts custom para acabar ignorando casi todo lo que useChat aporta
// (historial multi-turno, streaming de texto). fetch + ReadableStream son
// ~40 líneas sin dependencias. Nota: EventSource no sirve — solo hace GET y
// la api_key debe viajar en el body de un POST.
import { useCallback, useRef, useState } from "react";

import { URL_API, mensajeDeError } from "@/lib/api";
import type {
  EventoAgente,
  PasoProgreso,
  ProveedorId,
  RespuestaAgente,
} from "@/lib/tipos";

export type ParametrosBusqueda = {
  consulta: string;
  proveedor: ProveedorId;
  modelo: string;
  apiKey: string;
};

type Fase = "inactivo" | "buscando" | "listo" | "error";

function resumenEntrada(entrada: Record<string, unknown>): string {
  return Object.entries(entrada)
    .map(([clave, valor]) =>
      typeof valor === "object" && valor !== null
        ? `${clave}: ${resumenEntrada(valor as Record<string, unknown>)}`
        : `${clave}: ${String(valor)}`,
    )
    .join(", ");
}

function etiquetaDeTool(tool: string, entrada: Record<string, unknown>): string {
  if (tool === "filtrar_cartas") return "Filtrando cartas";
  if (tool === "buscar_semantica")
    return `Buscando por significado: “${entrada.texto_consulta ?? ""}”`;
  return tool;
}

export function useAgenteStream() {
  const [fase, setFase] = useState<Fase>("inactivo");
  const [pasos, setPasos] = useState<PasoProgreso[]>([]);
  const [resultado, setResultado] = useState<RespuestaAgente | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const idRef = useRef(0);

  const cancelar = useCallback(() => {
    abortRef.current?.abort();
    setFase("inactivo");
  }, []);

  const buscar = useCallback(async (params: ParametrosBusqueda) => {
    abortRef.current?.abort();
    const abort = new AbortController();
    abortRef.current = abort;
    idRef.current = 0;
    setFase("buscando");
    setPasos([]);
    setResultado(null);
    setError(null);

    const falla = (mensaje: string) => {
      setError(mensaje);
      setFase("error");
    };

    const procesa = (evento: EventoAgente) => {
      // Cada tool_use abre un paso; su tool_result lo cierra con el conteo.
      if (evento.tipo === "inicio") {
        setPasos([{ id: ++idRef.current, estado: "hecho",
                    etiqueta: `Agente iniciado (${evento.modelo})` }]);
      } else if (evento.tipo === "tool_use") {
        setPasos((p) => [
          ...p.map((x) => ({ ...x, estado: "hecho" as const })),
          { id: ++idRef.current, estado: "en_curso",
            etiqueta: etiquetaDeTool(evento.tool, evento.entrada),
            detalle: resumenEntrada(evento.entrada) },
        ]);
      } else if (evento.tipo === "tool_result") {
        setPasos((p) =>
          p.map((x, i) =>
            i === p.length - 1
              ? { ...x,
                  estado: evento.error ? "error" : "hecho",
                  detalle: evento.error
                    ? `error: ${evento.error}`
                    : `${x.detalle ?? ""} → ${evento.total} cartas` }
              : x,
          ),
        );
      } else if (evento.tipo === "error") {
        falla(mensajeDeError(evento.status, evento.detalle));
      } else if (evento.tipo === "respuesta") {
        setResultado(evento);
        setFase("listo");
      }
    };

    try {
      const res = await fetch(`${URL_API}/agente/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abort.signal,
        body: JSON.stringify({
          consulta: params.consulta,
          proveedor: params.proveedor,
          modelo: params.modelo || null,
          api_key: params.apiKey,
        }),
      });
      if (!res.ok || !res.body) {
        const cuerpo = await res.json().catch(() => null);
        falla(mensajeDeError(res.status, cuerpo?.detail));
        return;
      }

      // SSE a mano: acumular bytes, separar eventos por línea en blanco,
      // parsear cada "data: {...}".
      const lector = res.body.getReader();
      const decodificador = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await lector.read();
        if (done) break;
        buffer += decodificador.decode(value, { stream: true });
        const bloques = buffer.split("\n\n");
        buffer = bloques.pop() ?? "";
        for (const bloque of bloques) {
          const linea = bloque
            .split("\n")
            .find((l) => l.startsWith("data: "));
          if (!linea) continue;
          procesa(JSON.parse(linea.slice(6)) as EventoAgente);
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        falla("No se pudo conectar con la API. ¿Está corriendo el backend?");
      }
    }
  }, []);

  return { fase, pasos, resultado, error, buscar, cancelar };
}
