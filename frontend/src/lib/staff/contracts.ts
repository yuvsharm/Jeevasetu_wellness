export type StaffProfile = { id:string; user_id:string; staff_type:"MANAGER"|"PHYSIOTHERAPIST"; full_name:string; email:string; mobile:string; profile_photo:string; gender:string; date_of_birth:string; qualification:string; registration_number:string; experience_years:number; specialization_ids:string[]; languages_known:string[]; alternate_mobile:string; emergency_contact:string; current_address:string; city:string; pin_code:string; clinic:string|null; service_area_ids:string[]; availability:"AVAILABLE"|"BUSY"|"UNAVAILABLE"; is_online:boolean; joining_date:string; is_active:boolean; bio:string; documents:Array<{id:string;label:string;file:string}> };

export type StaffPage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: StaffProfile[];
};
