import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

export default function nextConfig(phase: string): NextConfig {
  const allowedDevOrigins = (process.env.NEXT_ALLOWED_DEV_ORIGINS ?? "")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean);

  return {
    // Keep the long-running dev compiler isolated from `next build`, which
    // replaces the production output directory while local UAT is running.
    distDir: phase === PHASE_DEVELOPMENT_SERVER ? ".next-dev" : ".next",
    output: "standalone",
    poweredByHeader: false,
    reactStrictMode: true,
    ...(phase === PHASE_DEVELOPMENT_SERVER && allowedDevOrigins.length > 0
      ? { allowedDevOrigins }
      : {}),
  };
}
