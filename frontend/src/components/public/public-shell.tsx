import type { ReactNode } from "react";
import { PublicFooter } from "./public-footer";
import { PublicHeader } from "./public-header";

export function PublicShell({ children }: { children: ReactNode }) {
  return <div className="public-site"><PublicHeader />{children}<PublicFooter /></div>;
}
