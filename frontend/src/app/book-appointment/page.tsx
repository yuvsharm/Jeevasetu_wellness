import { BookingForm } from "@/components/appointments/booking-form";
import { PageHero } from "@/components/public/page-hero";
import { PublicShell } from "@/components/public/public-shell";

export default async function BookAppointmentPage({ searchParams }: { searchParams: Promise<{ therapy?: string; package?: string; offer?: string }> }) {
  const { therapy = "", package: packageId = "", offer = "" } = await searchParams;
  return (
    <PublicShell>
      <main>
        <PageHero eyebrow="Quick Appointment" title="Request your preferred therapy, date, and time">
          Choose care for yourself or a family member using your verified customer profile.
        </PageHero>
        <section className="section pt-0">
          <div className="site-container max-w-4xl">
            <BookingForm initialTherapy={therapy} initialPackage={packageId} initialOffer={offer} />
          </div>
        </section>
      </main>
    </PublicShell>
  );
}
