/**
 * PlanProgress -- live step-by-step view of the planner's plan.
 *
 * Shown while the agent loop is running and a plan is active. Steps
 * before the active index render as complete; the active step is
 * highlighted; later steps are muted. When the agent goes off-plan
 * (step_index === null), an italicized note appears beneath the list.
 */
import type { TurnPlan } from "../../types/chat";

interface Props {
  plan: TurnPlan;
  activeStepIndex: number | null; // 1-based; null while idle or off-plan
  activeStepText: string | null; // off-plan note when step_index is null
}

export default function PlanProgress({
  plan,
  activeStepIndex,
  activeStepText,
}: Props) {
  const offPlan = activeStepIndex === null && !!activeStepText;

  return (
    <div className="rounded-2xl bg-indigo-50/60 border border-indigo-100 px-4 py-3 shadow-sm">
      {plan.goal && (
        <p className="text-xs uppercase tracking-wide text-indigo-500 font-medium mb-2">
          {plan.goal}
        </p>
      )}
      <ol className="space-y-1.5">
        {plan.steps.map((step, i) => {
          const idx = i + 1;
          const isComplete = activeStepIndex !== null && idx < activeStepIndex;
          const isActive = activeStepIndex === idx;
          return (
            <li
              key={`${idx}-${step}`}
              className="flex items-start gap-2 text-sm"
            >
              <span
                className={
                  "mt-0.5 inline-flex w-4 h-4 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold " +
                  (isComplete
                    ? "bg-indigo-500 border-indigo-500 text-white"
                    : isActive
                    ? "bg-white border-indigo-500 text-indigo-500 animate-pulse"
                    : "bg-white border-gray-300 text-gray-400")
                }
                aria-hidden
              >
                {isComplete ? "✓" : idx}
              </span>
              <span
                className={
                  isComplete
                    ? "text-gray-400 line-through"
                    : isActive
                    ? "text-gray-800 font-medium"
                    : "text-gray-500"
                }
              >
                {step}
              </span>
            </li>
          );
        })}
      </ol>
      {offPlan && (
        <p className="mt-2 text-xs italic text-gray-500">
          Adjusting: {activeStepText}
        </p>
      )}
    </div>
  );
}
