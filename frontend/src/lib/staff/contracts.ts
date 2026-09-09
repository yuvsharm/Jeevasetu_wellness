export type StaffProfile = { photo_url?:string; clinic_timezone?:string; operating_days?:Array<{weekday:number;is_open:boolean;opens_at:string|null;closes_at:string|null}>; upcoming_leave?:Array<{id:string;from_date:string;to_date:string}>; id:string; user_id:string; staff_type:"MANAGER"|"PHYSIOTHERAPIST"; full_name:string; email:string; mobile:string; profile_photo:string; gender:string; age?:number|null; date_of_birth:string; qualification:string; registration_number:string; experience_years:number; experience_months:number; specialization_ids:string[]; specialization_names:string[]; therapy_competency_ids:string[]; verified_therapy_ids:string[]; verified_therapy_names:string[]; profile_source:"PRACTITIONER_APPLICATION"|"STAFF_CREATED"; approved_weekly_rule_count:number; approval_status:"VERIFIED_APPROVED"|"PENDING_APPLICATION"|"REJECTED"|"NOT_APPLICABLE"; activation_status:"ACTIVATION_PENDING"|"ACCOUNT_ACTIVATED"; is_publicly_visible:boolean; languages_known:string[]; alternate_mobile:string; emergency_contact:string; current_address:string; city:string; pin_code:string; clinic:string|null; clinic_name:string|null; service_area_ids:string[]; availability:"AVAILABLE"|"BUSY"|"UNAVAILABLE"; is_online:boolean; joining_date:string; is_active:boolean; bio:string; documents:Array<{id:string;label:string;file:string}> };

export type StaffPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: StaffProfile[];
};
