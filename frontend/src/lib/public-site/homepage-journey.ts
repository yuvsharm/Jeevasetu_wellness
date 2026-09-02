export type JourneyStep = {
  number: string;
  title: string;
  description: string;
  image: string;
  imageAlt: string;
};

export const journeySteps: JourneyStep[] = [
  {
    number: "01",
    title: "Choose your therapy",
    description: "Browse therapies, session plans and available offers.",
    image: "/images/journey/choose-therapy.webp",
    imageAlt: "Customer comparing home-wellness services on a tablet",
  },
  {
    number: "02",
    title: "Select date & time",
    description: "Choose your preferred home-visit date and available service slot.",
    image: "/images/journey/select-date-time.webp",
    imageAlt: "Customer selecting an appointment date and time on a tablet",
  },
  {
    number: "03",
    title: "Login/Register & request booking",
    description: "Securely sign in or register and submit your appointment request.",
    image: "/images/journey/request-booking.webp",
    imageAlt: "Customer securely requesting a home-care appointment by mobile",
  },
  {
    number: "04",
    title: "JeevaSetu confirms your professional",
    description: "Our team reviews your request and assigns a suitable verified professional.",
    image: "/images/journey/confirm-professional.webp",
    imageAlt: "JeevaSetu coordinator confirming a suitable professional",
  },
  {
    number: "05",
    title: "Professional visits your home",
    description: "Your confirmed professional provides the scheduled service at your location.",
    image: "/images/journey/home-visit.webp",
    imageAlt: "Home-care professional arriving at a customer's home",
  },
  {
    number: "06",
    title: "Verify & complete",
    description: "Secure service verification confirms the visit and completion.",
    image: "/images/journey/verify-complete.webp",
    imageAlt: "Customer and professional confirming successful service completion",
  },
];
