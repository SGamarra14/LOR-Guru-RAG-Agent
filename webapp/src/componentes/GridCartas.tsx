import { TarjetaCarta } from "@/componentes/TarjetaCarta";
import type { Carta } from "@/lib/tipos";

export function GridCartas({ cartas }: { cartas: Carta[] }) {
  if (cartas.length === 0) return null;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      {cartas.map((carta) => (
        <TarjetaCarta key={carta.cardCode} carta={carta} />
      ))}
    </div>
  );
}
