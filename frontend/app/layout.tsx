import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono, IBM_Plex_Serif } from "next/font/google";
import "./globals.css";

/*
  Une seule superfamille, trois roles :
    - Sans  : interface
    - Mono  : tous les chiffres (tabulaires, donc alignes)
    - Serif : la these d'investissement, qui se lit comme une note de comite
*/
const sans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const mono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const serif = IBM_Plex_Serif({
  variable: "--font-plex-serif",
  subsets: ["latin"],
  weight: ["400", "500"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Comité Or — Décision de trading",
  description:
    "Huit agents d'analyse, une décision. Or (GC futures / XAU/USD), du 5 minutes au 4 heures.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body
        className={`${sans.variable} ${mono.variable} ${serif.variable} grain antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
