/**
 * PayloadRenderer — dispatches structured payloads to type-specific components.
 *
 * Known types get dedicated, rich renderers. Unknown types are handled by
 * the GenericPayloadView fallback, which renders tables for arrays and
 * definition lists for key-value objects — much better than raw JSON.
 */
import type { DailyPlanPayload, DailySchedulePayload, StructuredPayload } from "../../types/payloads";
import DailyPlanView from "./DailyPlanView";
import DailyScheduleView from "./DailyScheduleView";
import GenericPayloadView from "./GenericPayloadView";

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
      return <GenericPayloadView payload={payload} />;
  }
}
