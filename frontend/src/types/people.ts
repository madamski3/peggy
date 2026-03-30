export interface Person {
  id: string;
  name: string;
  relationship_type: string | null;
  description: string | null;
  contact_info: Record<string, string> | null;
  key_dates: Record<string, string> | null;
  preferences: Record<string, string> | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}
