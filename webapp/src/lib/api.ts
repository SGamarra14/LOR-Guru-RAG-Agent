// Cliente de la API de LoR Guru.
import type { Proveedor } from "./tipos";

// El backend vive en otro dominio (Vercel no hostea la API): la URL viene de
// entorno. En dev, .env.local con NEXT_PUBLIC_API_URL=http://localhost:8000.
export const URL_API =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function obtenerProveedores(): Promise<Proveedor[]> {
  const res = await fetch(`${URL_API}/proveedores`);
  if (!res.ok) throw new Error(`No se pudo cargar /proveedores (${res.status})`);
  return res.json();
}

// El backend (fase 2) ya hace el trabajo de extraer mensajes humanos del
// proveedor — aquí solo se les da contexto según el status. Nunca degradar a
// un "algo salió mal" genérico si hay un detalle utilizable.
export function mensajeDeError(status: number, detalle?: string): string {
  switch (status) {
    case 401:
      return "El proveedor rechazó tu API key. Revisa que sea la clave correcta para el proveedor elegido.";
    case 429:
      return (
        "El proveedor devolvió límite de cuota (429). Si usas un tier gratuito " +
        "(p. ej. Gemini free, ~20 solicitudes/día por modelo), es probable que la " +
        "hayas agotado: espera al reinicio diario, usa otro modelo o una clave de pago." +
        (detalle ? ` Detalle: ${detalle}` : "")
      );
    case 400:
      // El detail ya trae el mensaje humano extraído del proveedor
      // (p. ej. "credit balance is too low", "modelo inválido").
      return detalle ?? "El proveedor rechazó la petición.";
    case 422:
      return "La petición no pasó la validación. Revisa consulta, proveedor y API key.";
    case 502:
      return detalle ?? "El proveedor tuvo un error transitorio. Intenta de nuevo.";
    default:
      return detalle ?? `Error inesperado (${status}).`;
  }
}

// Las URLs de imagen del Data Dragon vienen con http:// en el dato; servirlas
// así en una página https sería contenido mixto (bloqueado por el navegador).
// El CDN sí sirve https — se reescribe aquí.
export function urlImagenSegura(url: string): string {
  return url.replace(/^http:\/\//, "https://");
}
