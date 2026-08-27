"use client";

import Link, { type LinkProps } from "next/link";
import type { AnchorHTMLAttributes, ReactNode } from "react";

import { useOptionalSession } from "@/components/auth/session-provider";
import { activeRoles } from "@/lib/auth/roles";

type Props = LinkProps & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, keyof LinkProps> & {
  children: ReactNode;
};

export function bookingDestination(intended: string, roles?: string[]) {
  if (roles?.includes("CUSTOMER")) return intended;
  if (roles?.length) return "/unauthorized";
  return `/customer-access?returnTo=${encodeURIComponent(intended)}`;
}

export function BookingLink({ href, children, ...props }: Props) {
  const session = useOptionalSession();
  const intended = typeof href === "string" ? href : href.pathname?.toString() || "/book-appointment";
  const roles = session?.data ? activeRoles(session.data.access.roles) : undefined;
  return <Link href={bookingDestination(intended, roles)} {...props}>{children}</Link>;
}
