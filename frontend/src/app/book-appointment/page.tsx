import { BookingForm } from "@/components/appointments/booking-form";
import { PageHero } from "@/components/public/page-hero";
import { PublicShell } from "@/components/public/public-shell";

export default async function BookAppointmentPage({ searchParams }: { searchParams: Promise<{ therapy?: string }> }) {
  const { therapy = "" } = await searchParams;
  return (
    <PublicShell>
      <main>
        <PageHero eyebrow="Quick Appointment" title="Request your preferred therapy, date, and time">
          Share your details, verify your mobile number, and send one clear request for review.
        </PageHero>
        <section className="section pt-0">
          <div className="site-container max-w-4xl">
            <BookingForm initialTherapy={therapy} quickMode />
          </div>
        </section>
      </main>
    </PublicShell>
  );
}