import type { Metadata } from "next";
import { Geist } from "next/font/google";
import type { ReactNode } from "react";

import { QueryProvider } from "@/components/providers/query-provider";
import { SessionProvider } from "@/components/auth/session-provider";
import "./globals.css";

const geist = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "NuriPain Ease | Home Physiotherapy & Wellness Care in Meerut", template: "%s | NuriPain Ease" },
  description: "Professional home physiotherapy and wellness services in Meerut with secure booking, transparent therapy information, and coordinated home visits.",
  keywords: ["home physiotherapy Meerut", "wellness home service", "physiotherapy at home", "NuriPain Ease"],
  openGraph: { title: "NuriPain Ease | Professional Care at Your Home", description: "Professional physiotherapy and wellness care coordinated for your home in Meerut.", type: "website", locale: "en_IN",images:[{url:"/images/ayurveda-hero.png",width:1200,height:630,alt:"NuriPain Ease home wellness care"}] },
  robots: { index: true, follow: true },
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [{ url: "/icons/nuripain-ease-mark.svg", type: "image/svg+xml", sizes: "any" }],
    shortcut: [{ url: "/icons/nuripain-ease-mark.svg", type: "image/svg+xml" }],
    apple: [{ url: "/icons/nuripain-ease-mark.svg", type: "image/svg+xml" }],
  },
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geist.variable} antialiased`}>
        <QueryProvider><SessionProvider>{children}</SessionProvider></QueryProvider>
      </body>
    </html>
  );
}
