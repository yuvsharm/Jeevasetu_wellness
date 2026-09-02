import { describe, expect, it } from "vitest";
import { getTherapyMedia, therapyMediaBySlug } from "@/lib/public-site/therapy-media";

const knownTherapySlugs = [
  "abhyang", "potli-massage", "shirodhara", "basti", "jannu-basti",
  "kati-basti", "griva-basti", "akshiyarpah-both-eyes", "nasya", "deeptishu-massage",
];

describe("therapy media mapping", () => {
  it("assigns a unique optimized image and meaningful alt text to every known therapy", () => {
    const media = knownTherapySlugs.map((slug) => therapyMediaBySlug[slug]);
    expect(media.every(Boolean)).toBe(true);
    expect(new Set(media.map((item) => item.src)).size).toBe(knownTherapySlugs.length);
    for (const item of media) {
      expect(item.src).toMatch(/^\/images\/therapies\/.+\.webp$/);
      expect(item.alt.length).toBeGreaterThan(20);
    }
  });

  it("uses a safe generic fallback only for unknown future therapies", () => {
    expect(getTherapyMedia("future-therapy", "Future Therapy")).toEqual({
      src: "/images/ayurveda-essentials.png",
      alt: "Future Therapy home wellness therapy preparation",
    });
  });
});
