export const publicNavigation = [
  { label: "Home", href: "/" },
  { label: "Therapies", href: "/therapies" },
  { label: "Plans & Offers", href: "/packages" },
  { label: "How It Works", href: "/#how-it-works" },
  { label: "Reviews", href: "/#reviews" },
  { label: "Contact Us", href: "/contact" },
  { label: "Join With Us", href: "/work-with-us" },
] as const;

export function isActivePublicRoute(pathname: string | null, href: string) {
  if (!pathname) return false;
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
