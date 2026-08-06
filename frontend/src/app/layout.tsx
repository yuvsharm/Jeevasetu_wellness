import type { Metadata } from "next";
import { Geist } from "next/font/google";
import type { ReactNode } from "react";

import { QueryProvider } from "@/components/providers/query-provider";
import "./globals.css";

const geist = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "JeevaSetu Wellness | Ayurvedic Home Service in Meerut", template: "%s | JeevaSetu Wellness" },
  description: "Premium Ayurvedic home-service therapies and wellness packages in Meerut. Healing Naturally. Living Better.",
  keywords: ["Ayurveda Meerut", "Ayurvedic home service", "wellness therapy", "JeevaSetu Wellness"],
  openGraph: { title: "JeevaSetu Wellness", description: "Healing Naturally. Living Better.", type: "website", locale: "en_IN" },
  robots: { index: true, follow: true },
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [{ url: "/favicon.ico", sizes: "any" }, { url: "/icons/icon-192.png", type: "image/png", sizes: "192x192" }],
    apple: [{ url: "/apple-icon.png", sizes: "180x180", type: "image/png" }],
  },
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geist.variable} antialiased`}>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
