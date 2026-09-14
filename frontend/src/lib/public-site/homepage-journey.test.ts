import { describe, expect, it } from "vitest";
import { journeySteps } from "@/lib/public-site/homepage-journey";

describe("homepage customer journey", () => {
  it("uses six concise customer-facing steps with unique optimized images", () => {
    expect(journeySteps.map((step) => step.title)).toEqual([
      "Choose your therapy",
      "Select date & time",
      "Login/Register & request booking",
      "JeevaSetu confirms your professional",
      "Professional visits your home",
      "Verify & complete",
    ]);
    expect(new Set(journeySteps.map((step) => step.image)).size).toBe(6);
    expect(journeySteps.every((step) => /\.(?:png|webp)$/.test(step.image) && step.imageAlt.length > 20)).toBe(true);
    expect(journeySteps.filter((step) => ["01", "03", "06"].includes(step.number)).map((step) => step.image)).toEqual([
      "/images/journey/jeevasetu-how-it-works-01.png",
      "/images/journey/jeevasetu-how-it-works-03.png",
      "/images/journey/jeevasetu-how-it-works-06.png",
    ]);
    expect(journeySteps.some((step) => /Manager confirms therapist|Verify mobile and book/.test(step.title))).toBe(false);
  });
});
