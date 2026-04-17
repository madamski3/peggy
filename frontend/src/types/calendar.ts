export interface CalendarEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  allDay: boolean;
  color?: string;
  extendedProps: {
    location: string;
    description: string;
    isAssistantCreated: boolean;
    status: string;
  };
}

export interface CalendarEventsResponse {
  connected: boolean;
  events: CalendarEvent[];
}
