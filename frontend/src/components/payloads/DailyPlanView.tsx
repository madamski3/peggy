/**
 * DailyPlanView — renders a proposed daily plan as a unified timeline.
 *
 * Shows all events for the day sorted chronologically. Visual styling
 * distinguishes proposed new events from already-scheduled ones:
 * - Proposed events: indigo accent (new additions)
 * - Scheduled todos: teal accent (already on calendar, linked to a todo)
 * - Calendar-only events: gray/muted (existing calendar events)
 */
import type { DailyPlanPayload, PlanEvent } from "../../types/payloads";

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function durationMinutes(start: string, end: string): number {
  return Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60000);
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function eventKind(ev: PlanEvent): "proposed" | "scheduled" | "calendar" {
  if (ev.proposed) return "proposed";
  if (ev.todo_id) return "scheduled";
  return "calendar";
}

function TimelineRow({ event }: { event: PlanEvent }) {
  const kind = eventKind(event);
  const duration = durationMinutes(event.scheduled_start, event.scheduled_end);

  const borderColor =
    kind === "proposed" ? "border-l-indigo-400"
    : kind === "scheduled" ? "border-l-teal-400"
    : "border-l-gray-300";

  const titleColor =
    kind === "calendar" ? "text-gray-500" : "text-gray-800";

  const badgeStyle =
    kind === "proposed" ? "bg-indigo-100 text-indigo-700"
    : kind === "scheduled" ? "bg-teal-100 text-teal-700"
    : "bg-gray-100 text-gray-500";

  const badgeLabel =
    kind === "proposed" ? "New"
    : kind === "scheduled" ? "Scheduled"
    : "Calendar";

  return (
    <div className={`flex items-start gap-3 py-2.5 border-l-2 pl-3 ${borderColor}`}>
      <div className="w-28 shrink-0 text-xs text-gray-500 pt-0.5">
        {formatTime(event.scheduled_start)} – {formatTime(event.scheduled_end)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-medium truncate ${titleColor}`}>
            {event.title}
          </span>
          <span className={`shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded ${badgeStyle}`}>
            {badgeLabel}
          </span>
        </div>
        {duration > 0 && (
          <div className="text-xs text-gray-400 mt-0.5">
            {formatDuration(duration)}
          </div>
        )}
      </div>
    </div>
  );
}

export default function DailyPlanView({ payload }: { payload: DailyPlanPayload }) {
  const events = [...(payload.events ?? [])].sort(
    (a, b) => new Date(a.scheduled_start).getTime() - new Date(b.scheduled_start).getTime()
  );

  if (events.length === 0) {
    return null;
  }

  const proposedCount = events.filter((e) => e.proposed).length;
  const existingCount = events.length - proposedCount;
  const parts = [];
  if (existingCount > 0) parts.push(`${existingCount} existing`);
  if (proposedCount > 0) parts.push(`${proposedCount} proposed`);

  return (
    <div className="mt-2 rounded-xl border border-gray-200 bg-gray-50/50 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          Proposed Plan
        </div>
        <div className="text-xs text-gray-400">
          {parts.join(" · ")}
        </div>
      </div>
      <div className="space-y-0.5">
        {events.map((event, idx) => (
          <TimelineRow key={idx} event={event} />
        ))}
      </div>
    </div>
  );
}
