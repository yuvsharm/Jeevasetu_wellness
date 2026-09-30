import Image from "next/image";
import Link from "next/link";

export function Wordmark({ compact = false, inverted = false, publicSite = false }: { compact?: boolean; inverted?: boolean; publicSite?: boolean }) {
  return (
    <Link href="/" className="inline-flex shrink-0 items-center rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-700">
      <Image
        src="/images/nuripain-ease-logo.svg"
        alt=""
        width={360}
        height={96}
        unoptimized
        priority={publicSite}
        className={`object-contain object-left ${compact ? "h-10 w-[150px]" : inverted ? "h-16 w-[240px] brightness-0 invert" : publicSite ? "h-11 w-[140px] sm:h-14 sm:w-[210px]" : "h-14 w-[210px]"}`}
        sizes={compact ? "150px" : inverted ? "240px" : publicSite ? "(max-width: 640px) 140px, 210px" : "210px"}
      />
      <span className="sr-only">NuriPain Ease home</span>
    </Link>
  );
}
