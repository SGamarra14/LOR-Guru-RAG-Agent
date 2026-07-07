"use client";
// Una carta del grid. El marco evoca una carta de LoR (borde dorado, esquinas
// marcadas, brillo cian al pasar el cursor) sin replicar el diseño de Riot.
import { useState } from "react";

import { urlImagenSegura } from "@/lib/api";
import type { Carta } from "@/lib/tipos";

export function TarjetaCarta({ carta }: { carta: Carta }) {
  const [conError, setConError] = useState(false);
  const src = urlImagenSegura(carta.imagen);

  return (
    <figure className="group marco-carta relative overflow-hidden transition-transform duration-200 hover:-translate-y-1">
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
      <figcaption className="border-t border-border/60 bg-card/95 px-3 py-2">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-display text-sm text-primary">{carta.nombre}</span>
          <span className="shrink-0 text-xs text-accent">{carta.coste} maná</span>
        </div>
        <div className="mt-0.5 truncate text-xs text-muted-foreground">
          {carta.regiones.join(" · ")} · {carta.tipo}
          {carta.keywords.length > 0 && ` · ${carta.keywords.join(", ")}`}
        </div>
      </figcaption>
    </figure>
  );
}
