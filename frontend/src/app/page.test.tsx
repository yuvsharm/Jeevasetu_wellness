import { render, screen } from "@testing-library/react";

import Home from "./page";

describe("Home", () => {
  it("presents the foundation status with an accessible heading", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", { level: 1, name: /professional physiotherapy care/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/service booking is not available yet/i)).toBeInTheDocument();
  });
});

