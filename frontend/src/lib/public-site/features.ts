export type PublicFeature = {
  slug: string;
  title: string;
  description: string;
  category: "care" | "platform" | "journey";
  mediaType: "image" | "video" | "graphic";
  image?: string;
  video?: string;
  poster?: string;
  visual?: string;
  href: string;
  ctaLabel: string;
  enabled: boolean;
  displayOrder: number;
};

export const publicFeatures: PublicFeature[] = [
  { slug: "physiotherapy-at-home", title: "Physiotherapy at Home", description: "Request professional physiotherapy support coordinated for a convenient home visit.", category: "care", mediaType: "image", image: "/images/ayurveda-home-service.png", href: "/therapies", ctaLabel: "Explore care", enabled: true, displayOrder: 10 },
  { slug: "wellness-therapies", title: "Ayurvedic & Wellness Therapies", description: "Explore JeevaSetu’s current home-service wellness catalogue and request the right experience.", category: "care", mediaType: "image", image: "/images/ayurveda-essentials.png", href: "/therapies", ctaLabel: "View therapies", enabled: true, displayOrder: 20 },
  { slug: "easy-appointment-booking", title: "Easy Appointment Booking", description: "Choose a live service, share your preferred schedule, and send one structured request.", category: "journey", mediaType: "graphic", visual: "01", href: "/book-appointment", ctaLabel: "Start booking", enabled: true, displayOrder: 30 },
  { slug: "reviewed-practitioners", title: "Practitioner at Your Doorstep", description: "Browse approved public practitioner profiles without exposing private application details.", category: "care", mediaType: "image", image: "/images/ayurveda-hero.png", href: "/practitioners", ctaLabel: "Meet practitioners", enabled: true, displayOrder: 40 },
  { slug: "otp-verified-service", title: "OTP-Verified Service", description: "A visit-specific verification step helps confirm the service journey before care begins.", category: "platform", mediaType: "graphic", visual: "OTP", href: "/why-choose-us", ctaLabel: "See how it works", enabled: true, displayOrder: 50 },
  { slug: "location-assisted-visit", title: "Location-Assisted Visit", description: "Location can be shared explicitly during an active accepted visit—never as background tracking.", category: "platform", mediaType: "graphic", visual: "⌖", href: "/why-choose-us", ctaLabel: "Explore the journey", enabled: true, displayOrder: 60 },
  { slug: "therapy-packages", title: "Therapy Packages", description: "Request a single session or discuss a multi-session wellness plan with JeevaSetu.", category: "care", mediaType: "graphic", visual: "5×", href: "/packages", ctaLabel: "View packages", enabled: true, displayOrder: 70 },
  { slug: "patient-feedback", title: "Patient Feedback", description: "Completed visits can support structured ratings and feedback within the care journey.", category: "journey", mediaType: "graphic", visual: "★", href: "/why-choose-us", ctaLabel: "Why JeevaSetu", enabled: true, displayOrder: 80 },
  { slug: "practitioner-enrollment", title: "Practitioner Enrollment", description: "Professionals can apply through a reviewed workflow before operational access is activated.", category: "platform", mediaType: "graphic", visual: "+", href: "/work-with-us", ctaLabel: "Work with us", enabled: true, displayOrder: 90 },
  { slug: "structured-digital-platform", title: "Structured Digital Care", description: "Booking, assignment, visit progress, verification, feedback, and operations stay connected.", category: "platform", mediaType: "graphic", visual: "JS", href: "/why-choose-us", ctaLabel: "Discover JeevaSetu", enabled: true, displayOrder: 100 },
  { slug: "future-video-story", title: "Future approved video", description: "Reserved for approved JeevaSetu media.", category: "care", mediaType: "video", video: "/media/future-approved.mp4", poster: "/images/ayurveda-home-service.png", href: "/therapies", ctaLabel: "Explore", enabled: false, displayOrder: 110 },
];

export function enabledPublicFeatures() {
  return publicFeatures.filter((feature) => feature.enabled).sort((a, b) => a.displayOrder - b.displayOrder);
}
