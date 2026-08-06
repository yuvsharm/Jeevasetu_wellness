export const contact = {
  phone: "9084401814",
  phoneHref: "tel:+919084401814",
  whatsapp: "https://wa.me/919084401814?text=Namaste%2C%20I%20would%20like%20to%20book%20an%20Ayurvedic%20home%20service.",
  email: "jeevasetu21@gmail.com",
  address: "163 C Block, Shastri Nagar, Meerut, Uttar Pradesh",
};

export const therapies = [
  { name: "Abhyang", price: "₹500", duration: "45–60 min", description: "A rhythmic full-body oil massage designed to support relaxation and everyday wellbeing.", benefits: ["Deep relaxation", "Supports mobility", "Nourishes the skin"] },
  { name: "Potli Massage", price: "₹600", duration: "45–60 min", description: "Warm herbal poultices are applied with skilled massage techniques for a comforting experience.", benefits: ["Soothing warmth", "Relaxed muscles", "Restorative care"] },
  { name: "Shirodhara", price: "₹1800", duration: "45 min", description: "A continuous stream of warm oil is gently directed over the forehead in a calm home setting.", benefits: ["Promotes calm", "Encourages rest", "Mindful relaxation"] },
  { name: "Basti", price: "₹500", duration: "30–40 min", description: "A traditional localized oil-retention therapy delivered after an individual consultation.", benefits: ["Focused care", "Warm oil support", "Personalized session"] },
  { name: "Jannu Basti", price: "₹2000", duration: "40–50 min", description: "A localized warm-oil therapy focused around the knee area for thoughtful, targeted care.", benefits: ["Knee-focused care", "Comforting warmth", "Supports flexibility"] },
  { name: "Kati Basti", price: "₹1900", duration: "40–50 min", description: "Warm medicated oil is retained over the lower back within a traditional dough boundary.", benefits: ["Lower-back focus", "Deep comfort", "Relaxing warmth"] },
  { name: "Griva Basti", price: "₹1900", duration: "40–50 min", description: "A carefully administered localized oil therapy focused on the neck and upper-back region.", benefits: ["Neck-focused care", "Comfort and ease", "Supports relaxation"] },
  { name: "Akshiyarpah (Both Eyes)", price: "₹1500", duration: "30–40 min", description: "A traditional eye-area wellness ritual performed with careful preparation and hygiene.", benefits: ["Restful ritual", "Gentle eye-area care", "Calming pause"] },
  { name: "Nasya", price: "₹1000", duration: "30 min", description: "A traditional Ayurvedic nasal-care ritual provided after suitability is discussed with you.", benefits: ["Traditional care", "Personal guidance", "Comfort-led session"] },
  { name: "Deeptishu Massage", price: "₹800", duration: "45–60 min", description: "A focused massage experience combining attentive technique with warm natural oils.", benefits: ["Personalized pressure", "Relaxing care", "At-home comfort"] },
] as const;

export const faqs = [
  ["How does an at-home session work?", "Choose a therapy and contact our team. We confirm your address, preferred time, suitability, and preparation guidance before the therapist visits."],
  ["Do I need to arrange oils or equipment?", "No. Our therapist brings the therapy essentials required for the confirmed service. We may ask you to keep fresh towels and a comfortable private space ready."],
  ["Are the therapies suitable for everyone?", "Suitability varies. Please share relevant health conditions, allergies, pregnancy, recent procedures, or current medical care before booking. Ayurveda wellness services do not replace medical treatment."],
  ["Which locations do you currently serve?", "We currently coordinate home services in and around Meerut. Contact us with your locality to confirm availability."],
  ["How should I prepare for a visit?", "Choose a warm, quiet room, avoid a heavy meal immediately before the session, and follow the personalized instructions shared during confirmation."],
  ["Can I customize a wellness package?", "Yes. Session count and therapy combinations can be discussed with our team based on your preferences and therapist guidance."],
] as const;

export const strengths = [
  ["Experienced Therapists", "Attentive professionals who respect your comfort, privacy, and home."],
  ["Authentic Ayurvedic Care", "Traditional wellness practices delivered with clear, modern service standards."],
  ["Natural Oils & Medicines", "Carefully selected therapy essentials prepared for your confirmed service."],
  ["Home Visit", "Wellness comes to you, without the stress of travel or waiting rooms."],
  ["Personalized Care", "Every visit begins with listening and is adapted to your comfort."],
  ["Hygiene & Safety", "Clean linens, organized equipment, and respectful in-home protocols."],
] as const;
