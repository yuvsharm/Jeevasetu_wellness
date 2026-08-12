import { activeRoles, dashboardDestination, primaryRole, roleDestinations } from "./roles";

describe("role navigation", () => {
  it("uses a deterministic order only for backend-confirmed active roles", () => {
    const values = [
      { role: "CUSTOMER" as const, is_active: true },
      { role: "OWNER" as const, is_active: false },
      { role: "MANAGER" as const, is_active: true },
    ];
    expect(activeRoles(values)).toEqual(["MANAGER", "CUSTOMER"]);
    expect(primaryRole(values)).toBe("MANAGER");
    expect(roleDestinations.MANAGER).toBe("/manager");
  });

  it("routes identities without an operational role to practitioner onboarding", () => {
    expect(dashboardDestination([])).toBe("/practitioner-application");
  });

  it("handles missing active access safely", () => {
    expect(primaryRole([])).toBeNull();
  });
});
