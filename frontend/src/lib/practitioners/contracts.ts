export type PractitionerStatus = "DRAFT" | "SUBMITTED" | "UNDER_REVIEW" | "CORRECTION_REQUIRED" | "APPROVED" | "REJECTED" | "WITHDRAWN";
export type PractitionerApplication = {
  id: string; status: PractitionerStatus; category: "PHYSIOTHERAPIST" | "WELLNESS"; full_legal_name: string;
  date_of_birth: string; gender: string; mobile_number: string; alternate_mobile: string; email: string;
  current_address: string; city: string; state: string; pin_code: string; highest_qualification: string;
  specialization: string; college_institute: string; awarding_body: string; passing_year: number;
  registration_number: string; registration_authority: string; registration_expiry: string | null;
  experience_years: number; experience_months: number; recent_organization: string; previous_experience: string;
  has_home_service_experience: boolean; bio: string; languages: string[]; clinic: string | null;
  availability_notes: string; last_completed_step: number; has_profile_photo: boolean;
  correction_reason: string; rejection_reason: string; submitted_at: string | null; updated_at: string;
  documents: Array<{id:string;kind:string;original_name:string;content_type:string;size_bytes:number;verification_status:string;created_at:string}>;
  competencies: Array<{id:string;therapy:string;therapy_name:string;experience_months:number;verification_status:string}>;
};
export type PublicPractitioner = { id:string; display_name:string; category:string; highest_qualification:string; qualification_specialization:string; experience_years:number; languages:string[]; bio:string; service_area:string; verified_services:string[]; photo_url:string };

