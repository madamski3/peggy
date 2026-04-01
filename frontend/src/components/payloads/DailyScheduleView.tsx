/**
 * DailyScheduleView — renders today's calendar events as a timeline card.
 *
 * Shows only calendar events (not tasks) in chronological order.
 */
import type { DailySchedulePayload, ScheduleItem } from "../../types/payloads";

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function ScheduleRow({ item }: { item: ScheduleItem }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-l-2 border-l-blue-400 pl-3">
      <div className="w-28 shrink-0 text-xs text-gray-500 pt-0.5">
        {formatTime(item.start)} – {formatTime(item.end)}
      </div>
      <div className="flex-1 min-w-0">
        <span className="text-sm text-gray-800 font-medium truncate">
          {item.title}
        </span>
      </div>
    </div>
  );
}

export default function DailyScheduleView({ payload }: { payload: DailySchedulePayload }) {
  if (!payload.items || payload.items.length === 0) {
    return null;
  }

  return (
    <div className="mt-2 rounded-xl border border-gray-200 bg-gray-50/50 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          Today's Calendar
        </div>
        <div className="text-xs text-gray-400">
          {payload.items.length} event{payload.items.length !== 1 ? "s" : ""}
        </div>
      </div>
      <div className="space-y-0.5">
        {payload.items.map((item, idx) => (
          <ScheduleRow key={idx} item={item} />
        ))}
      </div>
    </div>
  );
}
