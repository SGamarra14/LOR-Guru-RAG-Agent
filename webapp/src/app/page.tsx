"use client";
import { useEffect, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { FormularioBusqueda } from "@/componentes/FormularioBusqueda";
import { GridCartas } from "@/componentes/GridCartas";
import { PanelTransparencia } from "@/componentes/PanelTransparencia";
import { ProgresoAgente } from "@/componentes/ProgresoAgente";
import { useAgenteStream } from "@/hooks/useAgenteStream";
import { obtenerProveedores } from "@/lib/api";
import type { Proveedor } from "@/lib/tipos";

export default function Pagina() {
  const [proveedores, setProveedores] = useState<Proveedor[]>([]);
  const [errorCarga, setErrorCarga] = useState<string | null>(null);
  const { fase, pasos, resultado, error, buscar, cancelar } = useAgenteStream();

  useEffect(() => {
    obtenerProveedores()
      .then(setProveedores)
      .catch(() =>
        setErrorCarga(
          "No se pudo contactar a la API de LoR Guru. Verifica que el backend esté corriendo.",
        ),
      );
  }, []);

  return (
    <main className="mx-auto max-w-5xl space-y-8 px-4 py-10">
      <header className="space-y-2 text-center">
        <h1 className="font-display text-4xl tracking-wide text-primary sm:text-5xl">
          LoR Guru
        </h1>
        <p className="text-sm text-muted-foreground">
          Busca cartas de Legends of Runeterra describiéndolas en español — un
          agente decide entre filtros exactos y búsqueda semántica por ti.
        </p>
      </header>

      <section className="marco-panel p-6">
        {errorCarga ? (
          <Alert variant="destructive">
            <AlertTitle>Sin conexión con la API</AlertTitle>
            <AlertDescription>{errorCarga}</AlertDescription>
          </Alert>
        ) : (
          <FormularioBusqueda
            proveedores={proveedores}
            buscando={fase === "buscando"}
            onBuscar={buscar}
            onCancelar={cancelar}
          />
        )}
      </section>

      {(fase === "buscando" || pasos.length > 0) && (
        <section aria-live="polite">
          <ProgresoAgente pasos={pasos} />
        </section>
      )}

      {fase === "error" && error && (
        <Alert variant="destructive">
          <AlertTitle>La búsqueda no se pudo completar</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {fase === "listo" && resultado && (
        <section className="space-y-5">
          <div className="marco-panel space-y-3 p-6">
            <h2 className="font-display text-xl text-primary">
              Respuesta del agente
            </h2>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">
              {resultado.respuesta}
            </p>
            <PanelTransparencia
              llamadas={resultado.llamadas}
              metodo={resultado.metodo_cartas}
            />
          </div>
          <GridCartas cartas={resultado.cartas} />
        </section>
      )}

      <footer className="pt-6 text-center text-xs text-muted-foreground">
        Proyecto de portafolio. No afiliado a Riot Games. Los datos e imágenes
        de cartas provienen del Data Dragon público de Legends of Runeterra.
      </footer>
    </main>
  );
}
