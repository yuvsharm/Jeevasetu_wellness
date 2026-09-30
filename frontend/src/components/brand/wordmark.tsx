import Image from "next/image";
import Link from "next/link";

export function Wordmark({ compact = false, inverted = false, publicSite = false }: { compact?: boolean; inverted?: boolean; publicSite?: boolean }) {
  return (
    <Link href="/" className="inline-flex shrink-0 items-center rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-700">
      <Image
        src="/images/nuripain-ease-final-logo.png"
        alt=""
        width={1113}
        height={754}
        priority={publicSite}
        className={`object-contain object-left ${compact ? "size-12" : inverted ? "h-24 w-36" : publicSite ? "h-16 w-28 sm:h-20 sm:w-32" : "h-20 w-32"}`}
        sizes={compact ? "48px" : inverted ? "144px" : publicSite ? "(max-width: 640px) 112px, 128px" : "128px"}
      />
      <span className="sr-only">NuriPain Ease home</span>
    </Link>
  );
}
