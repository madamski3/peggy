export interface Todo {
  id: string;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  deadline: string | null;
  target_date: string | null;
  preferred_window: string | null;
  estimated_duration_minutes: number | null;
  energy_level: string | null;
  location: string | null;
  tags: string[] | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: string;
  todo_id: string;
  title: string;
  description: string | null;
  scheduled_start: string | null;
  scheduled_end: string | null;
  estimated_duration_minutes: number | null;
  actual_duration_minutes: number | null;
  status: string;
  completed_at: string | null;
  deferred_count: number;
  completion_notes: string | null;
  position: number | null;
  created_at: string;
  updated_at: string;
}
