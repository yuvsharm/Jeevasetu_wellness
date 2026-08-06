export type TherapyOption = { id: string; name: string; slug: string };
export type AppointmentRequest = {
  id: string; therapy: string; therapy_name: string; patient_name: string; age: number; gender: string;
  mobile_number: string; alternate_mobile: string; email: string; session_preference: string;
  preferred_date: string; preferred_time: string; problem_description: string; pain_area: string;
  problem_duration: string; doctor_reference: string; address: string; city: string; pin_code: string;
  landmark: string; google_map_link: string; status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
  owner_remarks: string; created_at: string; updated_at: string;
};

export type OperationalAppointment = {
  id: string;
  patient_identifier: string;
  patient_name: string;
  therapy_name: string;
  clinic_name: string;
  scheduled_start: string;
  scheduled_end: string;
  duration_minutes: number;
  status: "DRAFT" | "PENDING_ASSIGNMENT" | "SCHEDULED" | "CONFIRMED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED" | "NO_SHOW";
  physiotherapist_name: string | null;
  address_line_1?: string;
  address_line_2?: string;
  landmark?: string;
  city?: string;
  region?: string;
  pin_code?: string;
  physiotherapist_photo_url?: string | null;
};

export type OperationalAppointmentPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: OperationalAppointment[];
};
