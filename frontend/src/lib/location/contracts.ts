export type ServiceAddress = {
  address_line_1: string;
  address_line_2: string;
  landmark: string;
  city: string;
  region: string;
  pin_code: string;
  latitude: number | null;
  longitude: number | null;
  location_accuracy_meters: number | null;
  location_source: "MANUAL" | "DEVICE";
};

export const emptyServiceAddress = (): ServiceAddress => ({
  address_line_1: "", address_line_2: "", landmark: "", city: "", region: "",
  pin_code: "", latitude: null, longitude: null, location_accuracy_meters: null,
  location_source: "MANUAL",
});

export function isCompleteServiceAddress(value: ServiceAddress) {
  return Boolean(
    value.address_line_1.trim() &&
    value.city.trim() &&
    value.region.trim() &&
    /^[1-9]\d{5}$/.test(value.pin_code.trim()),
  );
}

export type ReverseGeocodeResult = Omit<ServiceAddress, "latitude" | "longitude" | "location_accuracy_meters" | "location_source"> & {
  display_address?: string;
  provider?: string;
};
