import { ProtectedPage } from "@/components/auth/protected-page";
import { CommercialOffers } from "@/components/public/therapy-grid";

export default function CustomerOffersPage() {
  return <ProtectedPage role="CUSTOMER" title="Offers & Packages">
    <section aria-labelledby="customer-offers-heading">
      <div className="mb-7 max-w-3xl">
        <h2 id="customer-offers-heading" className="text-3xl font-bold text-slate-950">Current offers and care packages</h2>
        <p className="mt-2 text-slate-600">Choose an active plan or offer to begin booking. Eligibility and the final payable amount are securely recalculated when you submit.</p>
      </div>
      <CommercialOffers />
    </section>
  </ProtectedPage>;
}
