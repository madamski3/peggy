/**
 * DailyPlanView — renders a proposed daily plan as a unified timeline.
 *
 * Shows existing calendar events (fixed anchors) alongside newly proposed
 * tasks, sorted chronologically. Visual styling distinguishes the two:
 * - Existing events: gray/muted (already on calendar)
 * - Proposed tasks: indigo accent (new additions)
 */
import type { DailyPlanPayload, ExistingEvent, PlanTask } from "../../types/payloads";

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

type TimelineItem =
  | { kind: "existing"; title: string; start: string; end: string }
  | { kind: "proposed"; title: string; start: string; end: string; duration: number };

function buildTimeline(payload: DailyPlanPayload): TimelineItem[] {
  const items: TimelineItem[] = [];

  for (const ev of payload.existing_events ?? []) {
    items.push({ kind: "existing", title: ev.title, start: ev.start, end: ev.end });
  }

  for (const planItem of payload.plan_items) {
    for (const task of planItem.tasks) {
      items.push({
        kind: "proposed",
        title: task.title,
        start: task.scheduled_start,
        end: task.scheduled_end,
        duration: task.estimated_duration_minutes,
      });
    }
  }

  items.sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime());
  return items;
}

function TimelineRow({ item }: { item: TimelineItem }) {
  const isExisting = item.kind === "existing";

  return (
    <div
      className={`flex items-start gap-3 py-2.5 border-l-2 pl-3 ${
        isExisting ? "border-l-gray-300" : "border-l-indigo-400"
      }`}
    >
      <div className="w-28 shrink-0 text-xs text-gray-500 pt-0.5">
        {formatTime(item.start)} – {formatTime(item.end)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span
            className={`text-sm font-medium truncate ${
              isExisting ? "text-gray-500" : "text-gray-800"
            }`}
          >
            {item.title}
          </span>
          <span
            className={`shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded ${
              isExisting
                ? "bg-gray-100 text-gray-500"
                : "bg-indigo-100 text-indigo-700"
            }`}
          >
            {isExisting ? "Existing" : "New"}
          </span>
        </div>
        {item.kind === "proposed" && item.duration > 0 && (
          <div className="text-xs text-gray-400 mt-0.5">
            {formatDuration(item.duration)}
          </div>
        )}
      </div>
    </div>
  );
}

export default function DailyPlanView({ payload }: { payload: DailyPlanPayload }) {
  const timeline = buildTimeline(payload);

  if (timeline.length === 0) {
    return null;
  }

  const existingCount = timeline.filter((i) => i.kind === "existing").length;
  const proposedCount = timeline.filter((i) => i.kind === "proposed").length;
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
        {timeline.map((item, idx) => (
          <TimelineRow key={idx} item={item} />
        ))}
      </div>
    </div>
  );
}
