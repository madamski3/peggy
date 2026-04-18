import { useRef, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import listPlugin from "@fullcalendar/list";
import type { EventClickArg, EventSourceFuncArg } from "@fullcalendar/core";
import { apiFetch } from "../../utils/api";
import type { CalendarEvent, CalendarEventsResponse } from "../../types/calendar";
import EventDetails from "./EventDetails";

const isMobile = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(max-width: 640px)").matches;

export default function CalendarPage() {
  const [selected, setSelected] = useState<CalendarEvent | null>(null);
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null);
  const [connected, setConnected] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const calendarRef = useRef<FullCalendar | null>(null);

  const fetchEvents = async (info: EventSourceFuncArg) => {
    setError(null);
    try {
      const params = new URLSearchParams({
        start: info.startStr,
        end: info.endStr,
      });
      const res = await apiFetch<CalendarEventsResponse>(
        `/calendar/events?${params.toString()}`,
      );
      setConnected(res.connected);
      return res.events;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load events");
      return [];
    }
  };

  const handleEventClick = (arg: EventClickArg) => {
    arg.jsEvent.preventDefault();
    const e = arg.event;
    const ev: CalendarEvent = {
      id: e.id,
      title: e.title,
      start: e.start?.toISOString() ?? "",
      end: e.end?.toISOString() ?? "",
      allDay: e.allDay,
      color: e.backgroundColor,
      extendedProps: {
        location: (e.extendedProps.location as string) ?? "",
        description: (e.extendedProps.description as string) ?? "",
        isAssistantCreated:
          (e.extendedProps.isAssistantCreated as boolean) ?? false,
        status: (e.extendedProps.status as string) ?? "",
      },
    };
    setSelected(ev);
    setAnchor({ x: arg.jsEvent.clientX, y: arg.jsEvent.clientY });
  };

  return (
    <div className="flex flex-col h-screen p-2 md:p-4 bg-surface-50">
      {!connected && (
        <div className="mb-3 p-3 rounded-md bg-amber-50 border border-amber-200 text-sm text-amber-900">
          Google Calendar isn't connected.{" "}
          <a
            href="/api/auth/google"
            className="underline font-medium"
          >
            Connect your Google account
          </a>{" "}
          to see your events here.
        </div>
      )}
      {error && (
        <div className="mb-3 p-3 rounded-md bg-red-50 border border-red-200 text-sm text-red-900">
          {error}
        </div>
      )}
      <div className="flex-1 min-h-0 bg-white rounded-lg shadow-sm p-2 md:p-3 overflow-hidden">
        <FullCalendar
          ref={calendarRef}
          plugins={[dayGridPlugin, timeGridPlugin, listPlugin]}
          initialView={isMobile() ? "listWeek" : "timeGridWeek"}
          headerToolbar={{
            left: "prev,next today",
            center: "title",
            right: "dayGridMonth,timeGridWeek,timeGridDay,listWeek",
          }}
          height="100%"
          expandRows
          nowIndicator
          events={fetchEvents}
          eventClick={handleEventClick}
          eventTimeFormat={{
            hour: "numeric",
            minute: "2-digit",
            meridiem: "short",
          }}
        />
      </div>
      {selected && (
        <EventDetails
          event={selected}
          anchor={anchor}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
