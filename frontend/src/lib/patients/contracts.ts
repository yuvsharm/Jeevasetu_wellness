export type PatientListItem = {
  id: string;
  patient_identifier: string;
  full_name: string;
  mobile_hint: string;
  gender: string;
  date_of_birth: string | null;
  age: number | null;
  clinic: string;
  clinic_name: string;
  is_active: boolean;
};

export type PatientPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: PatientListItem[];
};

export type PatientProfile = PatientListItem & {
  mobile_number: string;
  email: string;
  profile_photo_url: string | null;
  emergency_contact_name: string;
  emergency_contact_relationship: string;
  emergency_contact_mobile: string;
  guardian_name: string;
  guardian_relationship: string;
  guardian_mobile: string;
  addresses: Array<{
    id: string;
    label: string;
    address_line_1: string;
    address_line_2: string;
    landmark: string;
    city: string;
    region: string;
    pin_code: string;
    is_primary: boolean;
    is_active: boolean;
  }>;
};
