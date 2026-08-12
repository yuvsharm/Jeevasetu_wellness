import type { Role } from "@/lib/api/contracts";

export const roleDestinations: Record<Role, string> = {
  OWNER: "/owner",
  MANAGER: "/manager",
  PHYSIOTHERAPIST: "/physiotherapist",
  CUSTOMER: "/customer",
};

export const roleLabels: Record<Role, string> = {
  OWNER: "Owner",
  MANAGER: "Manager",
  PHYSIOTHERAPIST: "Physiotherapist",
  CUSTOMER: "Customer",
};

const rolePriority: Role[] = ["OWNER", "MANAGER", "PHYSIOTHERAPIST", "CUSTOMER"];

export function activeRoles(values: Array<{ role: Role; is_active: boolean }>): Role[] {
  const confirmed = new Set(values.filter((value) => value.is_active).map((value) => value.role));
  return rolePriority.filter((role) => confirmed.has(role));
}

export function primaryRole(values: Array<{ role: Role; is_active: boolean }>): Role | null {
  return activeRoles(values)[0] ?? null;
}

export function dashboardDestination(values: Array<{ role: Role; is_active: boolean }>): string {
  const role = primaryRole(values);
  return role ? roleDestinations[role] : "/practitioner-application";
}
