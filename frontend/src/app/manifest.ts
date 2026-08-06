import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "JeevaSetu Wellness",
    short_name: "JeevaSetu",
    description: "Premium Ayurvedic home-service wellness care in Meerut.",
    start_url: "/",
    display: "standalone",
    background_color: "#fffdf8",
    theme_color: "#0B6B3A",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
