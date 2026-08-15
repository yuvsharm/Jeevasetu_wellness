export type TherapyOption = { id: string; name: string; slug: string };
export type AppointmentRequest = {
  id: string; therapy: string; requested_therapies?: string[]; therapy_name: string; preferred_practitioner: string | null; patient_name: string; age: number; gender: string;
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
  assignment_status: "UNASSIGNED" | "PENDING" | "ACCEPTED" | "REJECTED";
  assigned_manager_name?: string | null;
  assignment_rejection_reason?: string;
  manager_remarks?: string;
  patient_mobile?: string;
  patient_age?: number | null;
  patient_gender?: string;
  problem_description?: string;
  pain_area?: string;
  google_map_link?: string;
  physiotherapist_qualification?: string;
  physiotherapist_experience_years?: number | null;
  address_line_1?: string;
  address_line_2?: string;
  landmark?: string;
  city?: string;
  region?: string;
  pin_code?: string;
  physiotherapist_photo_url?: string | null;
  reschedule_count?: number;
  cancellation_category?: "CUSTOMER_REQUEST" | "PHYSIOTHERAPIST_UNAVAILABLE" | "CLINIC_OPERATIONAL_ISSUE" | "SCHEDULING_CONFLICT" | "DUPLICATE_APPOINTMENT" | "OTHER" | "";
  visit_verification: VisitVerificationStatus;
  journey_status?: "NOT_STARTED" | "EN_ROUTE" | "ARRIVED";
  en_route_at?: string | null;
  arrived_at?: string | null;
  service_started_at?: string | null;
  completed_at?: string | null;
  rating_stars?: number | null;
  rating_comment?: string;
  payment_status?: "PENDING" | "PROCESSING" | "PAID" | "HELD" | null;
};

export type VisitVerificationStatus = {
  status: "NOT_READY" | "AWAITING_VERIFICATION" | "VERIFIED" | "EXPIRED" | "LOCKED";
  verified_at: string | null;
  expires_at: string | null;
  failed_attempt_warning: boolean;
  otp?: string;
};

export type PhysiotherapistWorkload = {
  id: string;
  full_name: string;
  clinic: string;
  active_assignments: number;
  upcoming_assignments: number;
};

export type OperationalAppointmentPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: OperationalAppointment[];
};

export type AppointmentAuditEvent = {
  id: string;
  event: string;
  outcome: "SUCCEEDED" | "REJECTED";
  actor_name: string;
  previous_status: string;
  new_status: string;
  previous_start: string | null;
  new_start: string | null;
  reason_category: string;
  override_used: boolean;
  rejection_code: string;
  created_at: string;
};

export type PractitionerPayment = {
  id: string; appointment: string; therapy_name: string; service_date: string;
  payable_amount: string | null; status: "PENDING" | "PROCESSING" | "PAID" | "HELD";
  paid_at: string | null; reference: string; note: string; updated_at: string;
};
