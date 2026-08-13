import { BookingForm } from "@/components/appointments/booking-form";
import { PageHero } from "@/components/public/page-hero";
import { PublicShell } from "@/components/public/public-shell";

export default async function BookAppointmentPage({ searchParams }: { searchParams: Promise<{ therapy?: string }> }) {
  const { therapy = "" } = await searchParams;
  return <PublicShell><main><PageHero eyebrow="Appointment request" title="Tell us how we can support you">Share your preferred therapy, time, and home-visit details. Our team will review your request before anything is confirmed.</PageHero><section className="section pt-0"><div className="site-container max-w-4xl"><BookingForm initialTherapy={therapy}/></div></section></main></PublicShell>;
}