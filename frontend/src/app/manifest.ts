import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "NuriPain Ease",
    short_name: "NuriPain Ease",
    description: "Premium Ayurvedic home-service wellness care in Meerut.",
    start_url: "/",
    display: "standalone",
    background_color: "#fffdf8",
    theme_color: "#0B6B3A",
    icons: [
      { src: "/icons/nuripain-ease-mark.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/icons/nuripain-ease-mark.svg", sizes: "any", type: "image/svg+xml", purpose: "maskable" },
    ],
  };
}
