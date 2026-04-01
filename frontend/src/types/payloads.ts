export interface PlanTask {
  title: string;
  scheduled_start: string;
  scheduled_end: string;
  estimated_duration_minutes: number;
}

export interface PlanItem {
  todo_id: string;
  todo_title?: string;
  tasks: PlanTask[];
  create_calendar_events: boolean;
}

export interface ExistingEvent {
  title: string;
  start: string;
  end: string;
}

export interface DailyPlanPayload {
  type: "daily_plan";
  existing_events?: ExistingEvent[];
  plan_items: PlanItem[];
}

export interface ScheduleItem {
  title: string;
  start: string;
  end: string;
}

export interface DailySchedulePayload {
  type: "daily_schedule";
  items: ScheduleItem[];
}

export interface GenericPayload {
  type: string;
  [key: string]: unknown;
}

export type StructuredPayload = DailyPlanPayload | DailySchedulePayload | GenericPayload;
