export const publicNavigation = [
  { label: "Home", href: "/" },
  { label: "About", href: "/about" },
  { label: "Therapies", href: "/therapies" },
  { label: "Services", href: "/therapies" },
  { label: "Packages", href: "/packages" },
  { label: "Why JeevaSetu", href: "/why-choose-us" },
  { label: "Practitioners", href: "/practitioners" },
  { label: "FAQ", href: "/faq" },
  { label: "Contact", href: "/contact" },
] as const;

export function isActivePublicRoute(pathname: string | null, href: string) {
  if (!pathname) return false;
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
