export interface ProfileField {
  field_key: string;
  value: unknown;
}

export interface ProfileSectionData {
  fields: Record<string, unknown>;
}

export interface ProfileData {
  identity: ProfileSectionData;
  contact: ProfileSectionData;
  household: ProfileSectionData;
  preferences: ProfileSectionData;
  career: ProfileSectionData;
  hobbies: ProfileSectionData;
  aspirations: ProfileSectionData;
  schedule: ProfileSectionData;
}

export interface Contact {
  id: string;
  name: string;
  type: string;
  description: string;
  value: string;
  primary: boolean;
}

export interface Pet {
  id: string;
  name: string;
  species: string;
  date_of_birth: string;
  sex: string;
  likes_dislikes: string;
  notes: string;
}

export interface Vehicle {
  id: string;
  name: string;
  year: string;
  make: string;
  model: string;
  vin: string;
  mileage: string;
  purchase_date: string;
  license_plate: string;
  history: string[];
}

export interface Role {
  id: string;
  name: string;
  title: string;
  employer: string;
  period: string;
  work_arrangement: string;
  experience: string[];
  notes: string;
}
