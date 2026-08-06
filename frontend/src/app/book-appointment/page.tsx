import { BookingForm } from "@/components/appointments/booking-form";
import { PageHero } from "@/components/public/page-hero";
import { PublicShell } from "@/components/public/public-shell";

export default function BookAppointmentPage() { return <PublicShell><main><PageHero eyebrow="Appointment request" title="Tell us how we can support you">Share your preferred therapy, time, and home-visit details. Our team will review your request before anything is confirmed.</PageHero><section className="section pt-0"><div className="site-container max-w-4xl"><BookingForm/></div></section></main></PublicShell>; }
