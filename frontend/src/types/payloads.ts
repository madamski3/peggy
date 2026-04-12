export interface PlanEvent {
  title: string;
  scheduled_start: string;
  scheduled_end: string;
  todo_id: string | null;
  proposed: boolean;
}

export interface DailyPlanPayload {
  type: "daily_plan";
  date?: string;
  events: PlanEvent[];
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
