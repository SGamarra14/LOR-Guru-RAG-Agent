import type { Metadata } from "next";
import { Cinzel, Nunito_Sans } from "next/font/google";
import "./globals.css";

// Dirección visual (GUIA_FASE3.md §7): display serif "de fantasía" para
// títulos (Cinzel, libre, espíritu cercano a los menús de LoR sin usar
// tipografías propietarias de Riot) + sans limpia para cuerpo/resultados.
const display = Cinzel({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["400", "600", "700"],
});

const cuerpo = Nunito_Sans({
  variable: "--font-cuerpo",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "LoR Guru — busca cartas en lenguaje natural",
  description:
    "Busca cartas de Legends of Runeterra describiéndolas en español. " +
    "Un agente con filtros exactos y búsqueda semántica encuentra por ti.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      className={`${display.variable} ${cuerpo.variable} h-full antialiased`}
    >
      <body className="fondo-grimorio min-h-full flex flex-col">{children}</body>
    </html>
  );
}
