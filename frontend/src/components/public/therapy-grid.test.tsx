import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CommercialOffers, TherapyGrid } from "@/components/public/therapy-grid";
import { therapyMediaBySlug } from "@/lib/public-site/therapy-media";

vi.mock("next/image", () => ({
  default: ({ src, alt }: { src: string; alt: string }) => {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt={alt} />;
  },
}));

const therapies = Object.keys(therapyMediaBySlug).map((slug, index) => ({
  id: `therapy-${index}`,
  name: slug === "akshiyarpah-both-eyes" ? "Akshiyarpah (Both Eyes)" : slug,
  slug,
  short_description: "Professional home care",
  detailed_description: "",
  benefits: [],
  default_duration_minutes: 45,
  base_price: "1000.00",
  is_active: true,
  is_publicly_visible: true,
  display_order: index,
}));

describe("TherapyGrid imagery", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the dedicated mapped asset for every current therapy card", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ therapies, packages: [], offers: [] }), { status: 200 }));
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><TherapyGrid compact /></QueryClientProvider>);
    const images = await screen.findAllByRole("img");
    expect(images).toHaveLength(10);
    expect(new Set(images.map((image) => image.getAttribute("src"))).size).toBe(10);
    for (const media of Object.values(therapyMediaBySlug)) {
      expect(screen.getByRole("img", { name: media.alt })).toHaveAttribute("src", media.src);
    }
  });

  it("shows the offer benefit, selection requirement, and inclusive customer dates", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(JSON.stringify({ therapies: [], packages: [], offers: [{
      id: "offer-1", title: "September special", promotional_text: "Choose your care",
      offer_type: "FIXED_DISCOUNT", discount_value: "800.00", fixed_price: null,
      minimum_therapy_count: 5, eligible_therapy_names: ["Abhyang", "Basti", "Nasya", "Shirodhara", "Potli Massage"],
      valid_from: "2020-01-01T00:00:00.000Z", valid_until: "2098-12-31T18:30:00.000Z",
    }] }), { status: 200 }));
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><CommercialOffers /></QueryClientProvider>);
    expect(await screen.findByText("₹800 OFF")).toBeInTheDocument();
    expect(screen.getByText("Choose any 5 eligible therapies")).toBeInTheDocument();
    expect(screen.getByText(/Valid 1 Jan 2020.*31 Dec 2098/)).toBeInTheDocument();
  });
});
