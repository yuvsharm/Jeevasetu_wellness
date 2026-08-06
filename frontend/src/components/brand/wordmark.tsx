import Image from "next/image";
import Link from "next/link";

export function Wordmark({ compact = false, inverted = false, publicSite = false }: { compact?: boolean; inverted?: boolean; publicSite?: boolean }) {
  return (
    <Link href="/" className="inline-flex shrink-0 items-center rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-700">
      <Image
        src="/images/logo.png"
        alt=""
        width={180}
        height={180}
        unoptimized
        priority={publicSite}
        className={`object-contain ${compact ? "size-12" : inverted ? "size-24" : publicSite ? "size-16 sm:size-20" : "size-20"}`}
        sizes={compact ? "48px" : inverted ? "96px" : publicSite ? "(max-width: 640px) 64px, 80px" : "80px"}
      />
      <span className="sr-only">JeevaSetu Wellness home</span>
    </Link>
  );
}
