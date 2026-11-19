import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Image Docker minimale : Next n'embarque que le runtime et les
  // dependances reellement utilisees. Indispensable sur un VPS partage
  // avec l'infra 22edges.
  output: "standalone",

  // Le monorepo vit a cote d'autres projets ; sans cela Next remonte
  // jusqu'au package-lock.json du Bureau et emet un avertissement.
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
