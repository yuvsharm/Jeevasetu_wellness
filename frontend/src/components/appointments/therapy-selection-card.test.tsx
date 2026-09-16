import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TherapySelectionCard } from "./therapy-selection-card";

const therapy = {
  id: "therapy-1",
  name: "Abhyang",
  slug: "abhyang",
  base_price: "500.00",
  short_description: "A gentle oil-massage therapy commonly considered for relaxation.",
  detailed_description: "A professional applies warm oil using rhythmic massage movements.",
  benefits: ["Everyday muscle tension", "Rest and relaxation"],
};

describe("TherapySelectionCard", () => {
  it("keeps the thumbnail, name, and price visible while information starts collapsed", () => {
    render(<TherapySelectionCard therapy={therapy} selected={false} onToggle={vi.fn()} />);
    expect(screen.getByRole("img", { name: /Abhyang oil massage/i })).toBeInTheDocument();
    expect(screen.getByText("Abhyang")).toBeInTheDocument();
    expect(screen.getByText("₹500")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Know about this therapy" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Commonly used for")).not.toBeInTheDocument();
  });

  it("expands all educational sections without changing selection", async () => {
    const onToggle = vi.fn();
    const user = userEvent.setup();
    render(<TherapySelectionCard therapy={therapy} selected={false} onToggle={onToggle} />);

    const disclosure = screen.getByRole("button", { name: "Know about this therapy" });
    await user.click(disclosure);

    expect(disclosure).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Commonly used for")).toBeInTheDocument();
    expect(screen.getByText("Common symptoms or concerns")).toBeInTheDocument();
    expect(screen.getByText("Everyday muscle tension")).toBeInTheDocument();
    expect(screen.getByText("What happens during the therapy")).toBeInTheDocument();
    expect(screen.getByText(/Suitability depends on your individual condition/i)).toBeInTheDocument();
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("selects from the card action by pointer or keyboard", async () => {
    const onToggle = vi.fn();
    const user = userEvent.setup();
    render(<TherapySelectionCard therapy={therapy} selected={false} onToggle={onToggle} />);

    const select = screen.getByRole("button", { name: "Select Abhyang" });
    await user.click(select);
    select.focus();
    await user.keyboard("{Enter}");
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it("switches to the safe local fallback when a therapy image fails", () => {
    render(<TherapySelectionCard therapy={therapy} selected={false} onToggle={vi.fn()} />);
    const image = screen.getByRole("img", { name: /Abhyang oil massage/i });
    expect(image).toHaveAttribute("src", expect.stringContaining("therapies%2Fabhyang.webp"));
    fireEvent.error(image);
    expect(image).toHaveAttribute("src", expect.stringContaining("ayurveda-essentials.png"));
  });

  it("uses conservative generic content when catalog education is missing", () => {
    render(<TherapySelectionCard therapy={{ id: "therapy-2", name: "Physiotherapy", slug: "physiotherapy", base_price: "0.00" }} selected={false} onToggle={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Know about this therapy" }));
    expect(screen.getByText(/part of an individual care or wellbeing plan/i)).toBeInTheDocument();
    expect(screen.getByText(/qualified professional discusses your needs/i)).toBeInTheDocument();
  });
});
