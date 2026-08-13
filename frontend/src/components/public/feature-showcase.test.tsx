import { render, screen } from "@testing-library/react";

import { enabledPublicFeatures, publicFeatures } from "@/lib/public-site/features";
import { FeatureShowcase } from "./feature-showcase";

describe("JeevaSetu feature showcase", () => {
  it("renders enabled features in configured order and excludes disabled media", () => {
    render(<FeatureShowcase/>);
    const expected = enabledPublicFeatures();
    const interactiveCards = document.querySelectorAll('.showcase-group:first-child [data-feature-slug]');
    expect([...interactiveCards].map((node) => node.getAttribute('data-feature-slug'))).toEqual(expected.map((feature) => feature.slug));
    expect(screen.queryByText("Future approved video")).not.toBeInTheDocument();
    expect(publicFeatures.some((feature) => !feature.enabled && feature.mediaType === "video")).toBe(true);
  });

  it("gives every visible card one valid existing-route action", () => {
    render(<FeatureShowcase/>);
    const links = document.querySelectorAll('.showcase-group:first-child a');
    expect(links).toHaveLength(enabledPublicFeatures().length);
    for (const link of links) {
      expect(link.getAttribute('href')).toMatch(/^\/(therapies|book-appointment|practitioners|why-choose-us|packages|work-with-us)$/);
      expect(link).not.toHaveAttribute('aria-hidden');
    }
  });

  it("keeps the duplicated animation track out of keyboard navigation", () => {
    render(<FeatureShowcase/>);
    const duplicates = document.querySelectorAll('.showcase-group[aria-hidden="true"] a');
    expect(duplicates).toHaveLength(enabledPublicFeatures().length);
    for (const link of duplicates) expect(link).toHaveAttribute('tabindex', '-1');
  });
});
