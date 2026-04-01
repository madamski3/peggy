/**
 * PayloadRenderer — dispatches structured payloads to type-specific components.
 *
 * Falls back to formatted JSON for unknown payload types so new types
 * are visible during development without crashing.
 */
import type { DailyPlanPayload, DailySchedulePayload, StructuredPayload } from "../../types/payloads";
import DailyPlanView from "./DailyPlanView";
import DailyScheduleView from "./DailyScheduleView";

interface Props {
  payload: Record<string, unknown>;
}

export default function PayloadRenderer({ payload }: Props) {
  const typed = payload as StructuredPayload;

  switch (typed.type) {
    case "daily_plan":
      return <DailyPlanView payload={typed as DailyPlanPayload} />;
    case "daily_schedule":
      return <DailyScheduleView payload={typed as DailySchedulePayload} />;
    default:
      // Fallback: render as formatted JSON for unknown payload types
      return (
        <div className="mt-2 rounded-xl border border-gray-200 bg-gray-50/50 p-3">
          <pre className="text-xs text-gray-600 whitespace-pre-wrap overflow-x-auto">
            {JSON.stringify(payload, null, 2)}
          </pre>
        </div>
      );
  }
}
