"use client";
// Una carta del grid. El marco (borde dorado, esquinas marcadas, glow cian al
// hover) abraza SOLO la imagen: el arte de la carta ya muestra nombre, coste,
// región y stats, así que no se repite esa metadata en texto — galería limpia.
// El fallback textual existe únicamente para imágenes rotas, donde no hay
// arte que cuente nada.
import { useState } from "react";

import { urlImagenSegura } from "@/lib/api";
import type { Carta } from "@/lib/tipos";

export function TarjetaCarta({ carta }: { carta: Carta }) {
  const [conError, setConError] = useState(false);
  const src = urlImagenSegura(carta.imagen);

  return (
    <figure
      className="group marco-carta relative overflow-hidden transition-transform duration-200 hover:-translate-y-1"
      title={`${carta.nombre} — ${carta.tipo}, coste ${carta.coste}`}
    >
      {conError || !src ? (
        <div className="flex aspect-[680/1024] flex-col items-center justify-center gap-2 bg-secondary p-4 text-center">
          <span className="font-display text-lg text-primary">{carta.nombre}</span>
          <span className="text-xs text-muted-foreground">{carta.descripcion}</span>
        </div>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- CDN externo de
        // Riot; no queremos el optimizador de next/image como intermediario.
        <img
          src={src}
          alt={`${carta.nombre} — ${carta.tipo}, coste ${carta.coste}`}
          loading="lazy"
          onError={() => setConError(true)}
          className="aspect-[680/1024] w-full object-cover"
        />
      )}
    </figure>
  );
}
