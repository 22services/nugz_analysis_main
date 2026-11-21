import type { Metadata } from "next";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-sans/latin-700.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/ibm-plex-mono/latin-600.css";
import "@fontsource/ibm-plex-serif/latin-400.css";
import "@fontsource/ibm-plex-serif/latin-500.css";
import "@fontsource/ibm-plex-serif/latin-400-italic.css";
import "./globals.css";

/*
  Une seule superfamille, trois roles :
    - Sans  : interface
    - Mono  : tous les chiffres (tabulaires, donc alignes)
    - Serif : la these d'investissement, qui se lit comme une note de comite

  Polices embarquees (@fontsource) plutot que next/font/google : le build
  Docker du VPS ne doit pas dependre d'un telechargement chez Google.
*/

export const metadata: Metadata = {
  title: "Comité Or — décision toutes les 15 min",
  description:
    "Or (COMEX) : VWAP, profil de volume, ATR et structure, plus le contexte OpenBB. Une décision par barre de 15 minutes.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body
        className="grain antialiased"
      >
        {children}
      </body>
    </html>
  );
}
