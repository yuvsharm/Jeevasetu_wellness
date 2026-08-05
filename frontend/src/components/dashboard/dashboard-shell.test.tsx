import { render, screen } from "@testing-library/react";

import { DashboardShell } from "./dashboard-shell";

describe("DashboardShell", () => {
  it.each(["OWNER", "MANAGER", "PHYSIOTHERAPIST", "CUSTOMER"] as const)(
    "renders the %s shell without fake operational values",
    (role) => {
      render(<DashboardShell role={role} />);
      expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(/dashboard shell/i);
      expect(screen.getAllByText(/underlying module is not implemented yet/i)).toHaveLength(6);
      expect(screen.queryByText(/₹|\$[0-9]|[0-9]+ appointments/i)).not.toBeInTheDocument();
    },
  );
});
