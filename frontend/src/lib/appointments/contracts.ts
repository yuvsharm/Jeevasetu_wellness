export type TherapyOption = { id: string; name: string; slug: string };
export type AppointmentRequest = {
  id: string; therapy: string; therapy_name: string; patient_name: string; age: number; gender: string;
  mobile_number: string; alternate_mobile: string; email: string; session_preference: string;
  preferred_date: string; preferred_time: string; problem_description: string; pain_area: string;
  problem_duration: string; doctor_reference: string; address: string; city: string; pin_code: string;
  landmark: string; google_map_link: string; status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
  owner_remarks: string; created_at: string; updated_at: string;
};
