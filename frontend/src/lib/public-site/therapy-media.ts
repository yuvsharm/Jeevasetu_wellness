export type TherapyMedia = { src: string; alt: string };

export const therapyMediaBySlug: Record<string, TherapyMedia> = {
  abhyang: {
    src: "/images/therapies/abhyang.webp",
    alt: "Professional demonstrating Abhyang oil massage in a clean home-wellness setting",
  },
  "potli-massage": {
    src: "/images/therapies/potli-massage-v2.webp",
    alt: "Potli Massage therapy being performed on a real patient",
  },
  shirodhara: {
    src: "/images/therapies/shirodhara.webp",
    alt: "Traditional Shirodhara oil stream directed toward the forehead",
  },
  basti: {
    src: "/images/therapies/basti-v2.webp",
    alt: "Localized Basti oil-retention therapy being performed on a real patient",
  },
  "jannu-basti": {
    src: "/images/therapies/jannu-basti-v2.webp",
    alt: "Jannu Basti warm oil therapy around the knee of a real patient",
  },
  "kati-basti": {
    src: "/images/therapies/kati-basti-v2.webp",
    alt: "Kati Basti warm oil therapy on the lower back of a real patient",
  },
  "griva-basti": {
    src: "/images/therapies/griva-basti.webp",
    alt: "Neck and upper-back-focused Griva Basti warm-oil therapy",
  },
  "akshiyarpah-both-eyes": {
    src: "/images/therapies/akshiyarpah-both-eyes.webp",
    alt: "Professional preparation for traditional both-eyes wellness care",
  },
  nasya: {
    src: "/images/therapies/nasya.webp",
    alt: "Professional Nasya nasal-care therapy preparation",
  },
  "deeptishu-massage": {
    src: "/images/therapies/deeptishu-massage.webp",
    alt: "Focused professional Deeptishu soft-tissue massage",
  },
};

export function getTherapyMedia(slug: string, therapyName: string): TherapyMedia {
  return therapyMediaBySlug[slug] ?? {
    src: "/images/ayurveda-essentials.png",
    alt: `${therapyName} home wellness therapy preparation`,
  };
}
