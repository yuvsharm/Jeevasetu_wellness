export type TherapyOption = { id:string; name:string; slug:string; short_description?:string; detailed_description?:string; benefits?:string[]; default_duration_minutes?:number|null; base_price?:string; is_active?:boolean; is_publicly_visible?:boolean; is_offer_free_addon?:boolean; display_order?:number; can_delete?:boolean; protected_references?:Record<string,number> };
export type TherapyPackage = { id:string; name:string; therapy:string; therapy_name:string; session_count:number; selling_price:string; regular_total:string; saving:string; discount_percentage:number; description:string; valid_from:string|null; valid_until:string|null; is_active:boolean; is_publicly_visible:boolean; display_order:number };
export type CommercialOffer = { id:string; title:string; promotional_text:string; offer_type:"PERCENTAGE"|"FIXED_DISCOUNT"|"FIXED_BUNDLE"|"FREE_THERAPY"|"FAMILY"|"THERAPY_DISCOUNT"|"FAMILY_FREE"; eligible_therapies:string[]; eligible_therapy_names:string[]; qualifying_package:string|null; minimum_therapy_count:number; maximum_therapy_count:number|null; discount_value:string; fixed_price:string|null; free_therapy:string|null; free_therapy_name:string; free_quantity:number; family_required:boolean; minimum_family_members:number; rule_config:{discount_type?:"PERCENTAGE"|"FIXED";therapy_discounts?:Array<{therapy_id:string;discount_type:"PERCENTAGE"|"FIXED";discount:number}>}; valid_from:string|null; valid_until:string|null; is_active:boolean; is_publicly_visible:boolean; display_order:number; created_at?:string; updated_at?:string; can_delete?:boolean; protected_references?:Record<string,number> };
export type CommercialCatalog = { therapies:TherapyOption[]; packages:TherapyPackage[]; offers:CommercialOffer[] };
export type CommercialQuote = { therapy_ids:string[]; therapy_names:string[]; therapy_prices:Record<string,string>; package_id:string|null; package_name:string; offer_id:string|null; offer_title:string; session_count:number; regular_amount:string; discount_amount:string; final_amount:string; free_benefits:Array<{therapy_id:string;therapy_name:string;quantity:number;unit_price?:string;duration_minutes?:number}>; duration_minutes:number };
export type AppointmentRequest = {
  id: string; therapy: string; requested_therapies?: string[]; requested_therapy_names?: string[]; requested_duration_minutes?: number; family_member?: string | null; selected_package?:string|null; selected_offer?:string|null; commercial_snapshot?:CommercialQuote; regular_amount?:string|null; discount_amount?:string|null; final_amount?:string|null; therapy_name: string; preferred_practitioner: string | null; patient_name: string; age: number; gender: string;
  mobile_number: string; alternate_mobile: string; email: string; session_preference: string;
  preferred_date: string; preferred_time: string; problem_description: string; pain_area: string;
  problem_duration: string; doctor_reference: string; address: string; city: string; pin_code: string;
  landmark: string; google_map_link: string; status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED";
  owner_remarks: string; rejection_category?: string; rejection_customer_reason?: string; created_at: string; updated_at: string;
  family_member_name?:string; appointment?:OperationalAppointment|null;
  timeline?:Array<{key:string;label:string;at:string|null}>;
};

export type OperationalAppointment = {
  id: string;
  originating_request?: string | null;
  requested_at?: string | null;
  created_at?: string;
  updated_at?: string;
  clinic?: string;
  patient_identifier: string;
  patient_name: string;
  patient_mobile?: string;
  patient_email?: string;
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
  patient_age?: number | null;
  patient_gender?: string;
  problem_description?: string;
  requested_therapy_names?: string[];
  pain_area?: string;
  google_map_link?: string;
  physiotherapist_qualification?: string;
  physiotherapist_experience_years?: number | null;
  physiotherapist_age?:number|null;
  physiotherapist_specialization?:string;
  physiotherapist_expertise?:string[];
  physiotherapist_rating?:number|null;
  physiotherapist_review_count?:number;
  address_line_1?: string;
  address_line_2?: string;
  landmark?: string;
  city?: string;
  region?: string;
  pin_code?: string;
  physiotherapist_photo_url?: string | null;
  reschedule_count?: number;
  cancellation_category?: "CUSTOMER_REQUEST" | "PHYSIOTHERAPIST_UNAVAILABLE" | "CLINIC_OPERATIONAL_ISSUE" | "SCHEDULING_CONFLICT" | "DUPLICATE_APPOINTMENT" | "OTHER" | "";
  journey_status?: "NOT_STARTED" | "EN_ROUTE" | "REACHED";
  en_route_at?: string | null;
  service_started_at?: string | null;
  completed_at?: string | null;
  rating_stars?: number | null;
  rating_comment?: string;
  payment_status?: "PENDING" | "PAID" | null;
  payment_amount_due?: string | null;
  payment_paid_at?: string | null;
  payment_confirmed_by?: string;
  payment_qr_available?: boolean;
  rating?: CustomerReview | null;
  reminders?: Array<{kind:"HOURS_24"|"HOURS_2";scheduled_for:string;status:"PENDING"|"SENT"}>;
};

export type AppointmentRequestPage = {
  count:number;
  next:string|null;
  previous:string|null;
  results:AppointmentRequest[];
};

export type CustomerReview = { id:string; appointment:string; stars:number; comment:string; moderation_status:"PENDING"|"APPROVED"|"HIDDEN"; status_display:string; moderation_reason:string; created_at:string };
export type ReviewItem = { id:string; stars:number; comment:string; moderation_status:"PENDING"|"APPROVED"|"HIDDEN"; moderation_reason:string; customer_display_name:string; physiotherapist_name:string; appointment_date:string; therapy_name:string; created_at:string };
export type ReviewSummary = { average_rating:number|null; review_count:number; reviews:ReviewItem[] };

export type PhysiotherapistWorkload = {
  id: string;
  full_name: string;
  clinic: string;
  active_assignments: number;
  upcoming_assignments: number;
  today_assignments: number;
  qualification: string;
  availability: "AVAILABLE" | "BUSY" | "UNAVAILABLE";
  is_online: boolean;
  service_areas: string[];
  specialties: string[];
  has_photo: boolean;
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
  previous_physiotherapist_name?: string | null;
  new_physiotherapist_name?: string | null;
  reason?: string;
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
