import Link from "next/link";
import { PublicShell } from "@/components/public/public-shell";

export default function NotFound() {
  return <PublicShell><main className="grid min-h-[65vh] place-items-center bg-[#f7f3e9] px-6 text-center"><section><p className="eyebrow">404 · Lost in the leaves</p><h1 className="mt-4 font-serif text-5xl text-[#103c27]">This path needs a little healing.</h1><p className="mt-4 text-[#5b6c63]">The page you requested could not be found.</p><Link href="/" className="button-primary mt-8">Return home</Link></section></main></PublicShell>;
}
