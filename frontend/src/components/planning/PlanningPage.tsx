import { useEffect, useState } from "react";
import { apiFetch } from "../../utils/api";
import type { ReviewTodo } from "../../types/todos";
import type {
  DailyPlanPayload,
  ExistingEvent,
  PlanItem,
} from "../../types/payloads";

/* ── Types ──────────────────────────────────────────────────────── */

interface ReviewItem {
  todo: ReviewTodo;
  action: "complete" | "reschedule";
  notes: string;
}

interface StoredPlan {
  id: string;
  plan_date: string;
  status: string;
  proposal: DailyPlanPayload;
  spoken_summary: string | null;
}

interface SubmitResult {
  review: { completed: number; rescheduled: number };
  plan: { items_created: number; events_created: number };
}

/* ── Helpers ─────────────────────────────────────────────────────── */

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatDuration(min: number) {
  if (min < 60) return `${min}m`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

/* ── Component ───────────────────────────────────────────────────── */

function toLocalDateStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function PlanningPage() {
  const todayStr = toLocalDateStr();
  const [selectedDate, setSelectedDate] = useState(todayStr);
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const isToday = selectedDate === todayStr;

  const [step, setStep] = useState<1 | 2>(1);
  const [reviewItems, setReviewItems] = useState<ReviewItem[]>([]);
  const [reviewDate, setReviewDate] = useState("");
  const [plan, setPlan] = useState<StoredPlan | null>(null);
  const [approvedTodoIds, setApprovedTodoIds] = useState<Set<string>>(
    new Set()
  );
  const [loaded, setLoaded] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [refining, setRefining] = useState(false);
  const [result, setResult] = useState<SubmitResult | null>(null);

  const [error, setError] = useState<string | null>(null);

  // Fetch available plan dates on mount
  useEffect(() => {
    apiFetch<{ dates: string[] }>("/planning/dates").then((data) =>
      setAvailableDates(data.dates)
    );
  }, []);

  // Fetch data when selectedDate changes
  useEffect(() => {
    setLoaded(false);
    setError(null);
    setResult(null);

    if (isToday) {
      apiFetch<{
        review: { todos: ReviewTodo[]; review_date: string };
        plan: StoredPlan | null;
      }>("/planning/today")
        .then((data) => {
          setReviewItems(
            data.review.todos.map((t) => ({ todo: t, action: "complete", notes: "" }))
          );
          setReviewDate(data.review.review_date);
          setPlan(data.plan);
          const planItems = data.plan?.proposal?.plan_items ?? [];
          if (planItems.length > 0) {
            setApprovedTodoIds(new Set(planItems.map((i) => i.todo_id)));
          }
          if (data.review.todos.length === 0) {
            setStep(2);
          } else {
            setStep(1);
          }
          setLoaded(true);
        })
        .catch((err) => {
          console.error("Failed to load planning data:", err);
          setError("Failed to load planning data. Please try refreshing.");
          setLoaded(true);
        });
    } else {
      setReviewItems([]);
      setStep(2);
      apiFetch<StoredPlan>(`/planning/history/${selectedDate}`)
        .then((data) => {
          setPlan(data);
          const planItems = data?.proposal?.plan_items ?? [];
          if (planItems.length > 0) {
            setApprovedTodoIds(new Set(planItems.map((i) => i.todo_id)));
          }
          setLoaded(true);
        })
        .catch(() => {
          setPlan(null);
          setLoaded(true);
        });
    }
  }, [selectedDate]);

  function updateReviewItem(idx: number, patch: Partial<ReviewItem>) {
    setReviewItems((prev) =>
      prev.map((item, i) => (i === idx ? { ...item, ...patch } : item))
    );
  }

  function toggleTodoApproval(todoId: string) {
    setApprovedTodoIds((prev) => {
      const next = new Set(prev);
      if (next.has(todoId)) next.delete(todoId);
      else next.add(todoId);
      return next;
    });
  }

  async function handleRegenerate() {
    setRegenerating(true);
    try {
      const newPlan = await apiFetch<StoredPlan>("/planning/regenerate", {
        method: "POST",
      });
      setPlan(newPlan);
      setApprovedTodoIds(
        new Set((newPlan.proposal.plan_items ?? []).map((i) => i.todo_id))
      );
    } finally {
      setRegenerating(false);
    }
  }

  async function handleRefine() {
    if (!feedback.trim() || !plan) return;
    setRefining(true);
    try {
      const updated = await apiFetch<StoredPlan>("/planning/refine", {
        method: "POST",
        body: JSON.stringify({
          feedback: feedback.trim(),
          current_proposal: plan.proposal,
        }),
      });
      setPlan(updated);
      setApprovedTodoIds(
        new Set((updated.proposal.plan_items ?? []).map((i) => i.todo_id))
      );
      setFeedback("");
    } finally {
      setRefining(false);
    }
  }

  async function handleSubmit() {
    setSubmitting(true);
    try {
      const approvedItems = plan
        ? (plan.proposal.plan_items ?? []).filter((i) =>
            approvedTodoIds.has(i.todo_id)
          )
        : [];

      const submittedItems = approvedItems.length > 0 ? approvedItems : null;
      const res = await apiFetch<SubmitResult>("/planning/submit", {
        method: "POST",
        body: JSON.stringify({
          review_items: reviewItems.map((item) => ({
            todo_id: item.todo.id,
            action: item.action,
            completion_notes: item.notes || null,
          })),
          approved_plan_items: submittedItems,
          plan_id: plan?.id ?? null,
        }),
      });
      // Update local plan to reflect only what was approved
      if (plan) {
        setPlan({
          ...plan,
          status: "approved",
          proposal: {
            ...plan.proposal,
            plan_items: submittedItems ?? [],
          },
        });
      }
      setResult(res);
    } finally {
      setSubmitting(false);
    }
  }

  /* ── Render states ─────────────────────────────────────────────── */

  if (!loaded) {
    return <div className="py-12 text-center text-gray-400">Loading...</div>;
  }

  if (error) {
    return (
      <div className="py-12 text-center">
        <p className="text-red-600">{error}</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Retry
        </button>
      </div>
    );
  }

  if (result) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-800">Daily Planning</h1>
          <DateNavigator
            selectedDate={selectedDate}
            availableDates={availableDates}
            todayStr={todayStr}
            onChange={setSelectedDate}
          />
        </div>
        <SuccessView result={result} plan={plan} />
      </div>
    );
  }

  const todayApproved = isToday && plan?.status === "approved";

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-800">Daily Planning</h1>
          <DateNavigator
            selectedDate={selectedDate}
            availableDates={availableDates}
            todayStr={todayStr}
            onChange={setSelectedDate}
          />
        </div>
        {isToday && !todayApproved && (
          <StepIndicator step={step} hasReview={reviewItems.length > 0} />
        )}
        {(!isToday || todayApproved) && plan && (
          <p className="text-xs text-gray-400 mt-2">
            {plan.status === "approved" ? "Approved" : "Proposed"} plan
          </p>
        )}
      </div>

      {isToday && !todayApproved && step === 1 && (
        <ReviewStep
          items={reviewItems}
          reviewDate={reviewDate}
          onUpdate={updateReviewItem}
          onContinue={() => setStep(2)}
        />
      )}

      {isToday && !todayApproved && step === 2 && (
        <PlanStep
          plan={plan}
          approvedTodoIds={approvedTodoIds}
          onToggle={toggleTodoApproval}
          regenerating={regenerating}
          onRegenerate={handleRegenerate}
          feedback={feedback}
          onFeedbackChange={setFeedback}
          refining={refining}
          onRefine={handleRefine}
          submitting={submitting}
          onSubmit={handleSubmit}
          onBack={reviewItems.length > 0 ? () => setStep(1) : undefined}
        />
      )}

      {(!isToday || todayApproved) && (
        <HistoricalPlanView plan={plan} />
      )}
    </div>
  );
}

/* ── Step Indicator ──────────────────────────────────────────────── */

function StepIndicator({
  step,
  hasReview,
}: {
  step: 1 | 2;
  hasReview: boolean;
}) {
  return (
    <div className="flex gap-4 mt-2">
      {hasReview && (
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded-full ${
            step === 1
              ? "bg-blue-100 text-blue-700"
              : "bg-gray-100 text-gray-400"
          }`}
        >
          1. Review
        </span>
      )}
      <span
        className={`text-xs font-medium px-2 py-0.5 rounded-full ${
          step === 2
            ? "bg-blue-100 text-blue-700"
            : "bg-gray-100 text-gray-400"
        }`}
      >
        {hasReview ? "2. Plan" : "Plan"}
      </span>
    </div>
  );
}

/* ── Date Navigator ─────────────────────────────────────────────── */

function DateNavigator({
  selectedDate,
  availableDates,
  todayStr,
  onChange,
}: {
  selectedDate: string;
  availableDates: string[];
  todayStr: string;
  onChange: (d: string) => void;
}) {
  // All navigable dates: available dates + today, deduplicated and sorted desc
  const allDates = [...new Set([todayStr, ...availableDates])].sort().reverse();
  const currentIdx = allDates.indexOf(selectedDate);

  const canGoNewer = currentIdx > 0;
  const canGoOlder = currentIdx < allDates.length - 1;

  const label = selectedDate === todayStr
    ? "Today"
    : new Date(selectedDate + "T12:00:00").toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
      });

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => canGoOlder && onChange(allDates[currentIdx + 1])}
        disabled={!canGoOlder}
        className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-30"
        title="Older"
      >
        &larr;
      </button>
      <span className="text-sm text-gray-600 min-w-[6rem] text-center font-medium">
        {label}
      </span>
      <button
        onClick={() => canGoNewer && onChange(allDates[currentIdx - 1])}
        disabled={!canGoNewer}
        className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-30"
        title="Newer"
      >
        &rarr;
      </button>
      {selectedDate !== todayStr && (
        <button
          onClick={() => onChange(todayStr)}
          className="ml-2 text-xs text-blue-600 hover:text-blue-700"
        >
          Today
        </button>
      )}
    </div>
  );
}

/* ── Historical Plan View (read-only) ──────────────────────────── */

function HistoricalPlanView({ plan }: { plan: StoredPlan | null }) {
  if (!plan) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
        <p className="text-gray-500">No plan found for this date</p>
      </div>
    );
  }

  const proposal = plan.proposal;
  const existingEvents = proposal?.existing_events ?? [];
  const planItems = proposal?.plan_items ?? [];

  type TimelineEntry =
    | { kind: "existing"; title: string; start: string; end: string }
    | {
        kind: "planned";
        todoTitle: string;
        title: string;
        start: string;
        end: string;
        duration: number;
      };

  const timeline: TimelineEntry[] = [];

  for (const ev of existingEvents) {
    timeline.push({ kind: "existing", title: ev.title, start: ev.start, end: ev.end });
  }

  for (const item of planItems) {
    for (const task of item.tasks ?? []) {
      timeline.push({
        kind: "planned",
        todoTitle: item.todo_title ?? "",
        title: task.title,
        start: task.scheduled_start,
        end: task.scheduled_end,
        duration: task.estimated_duration_minutes,
      });
    }
  }

  timeline.sort(
    (a, b) => new Date(a.start).getTime() - new Date(b.start).getTime()
  );

  return (
    <div className="space-y-4">
      {plan.spoken_summary && (
        <p className="text-sm text-gray-600 italic">{plan.spoken_summary}</p>
      )}

      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
          {plan.status === "approved" ? "Approved" : "Proposed"} Plan
        </div>

        {timeline.length === 0 ? (
          <p className="text-sm text-gray-400 py-4 text-center">
            No events or tasks in this plan
          </p>
        ) : (
          <div className="space-y-0.5">
            {timeline.map((entry, idx) => (
              <div
                key={idx}
                className={`flex items-start gap-3 py-2.5 border-l-2 pl-3 ${
                  entry.kind === "existing"
                    ? "border-l-gray-300"
                    : "border-l-indigo-400"
                }`}
              >
                <div className="w-28 shrink-0 text-xs text-gray-500 pt-0.5">
                  {formatTime(entry.start)} – {formatTime(entry.end)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-medium truncate ${
                      entry.kind === "existing" ? "text-gray-500" : "text-gray-800"
                    }`}>
                      {entry.title}
                    </span>
                    <span className={`shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded ${
                      entry.kind === "existing"
                        ? "bg-gray-100 text-gray-500"
                        : "bg-indigo-100 text-indigo-700"
                    }`}>
                      {entry.kind === "existing" ? "Calendar" : "Planned"}
                    </span>
                  </div>
                  {entry.kind === "planned" && (
                    <div className="text-xs text-gray-400 mt-0.5">
                      {entry.todoTitle && `${entry.todoTitle} · `}
                      {entry.duration > 0 && formatDuration(entry.duration)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Step 1: Yesterday's Review ──────────────────────────────────── */

function ReviewStep({
  items,
  reviewDate,
  onUpdate,
  onContinue,
}: {
  items: ReviewItem[];
  reviewDate: string;
  onUpdate: (idx: number, patch: Partial<ReviewItem>) => void;
  onContinue: () => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-500">
        Yesterday ({reviewDate}) — {items.length} task
        {items.length !== 1 && "s"} to review
      </p>

      {items.map((item, i) => (
        <div
          key={item.todo.id}
          className={`bg-white rounded-lg border p-4 transition-colors ${
            item.action === "reschedule"
              ? "border-amber-300"
              : "border-gray-200"
          }`}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <p className="font-medium text-gray-800">{item.todo.title}</p>
              {item.todo.parent_title && (
                <p className="text-xs text-gray-400 mt-0.5">
                  {item.todo.parent_title}
                </p>
              )}
              {item.todo.scheduled_start && (
                <p className="text-xs text-gray-400 mt-0.5">
                  {formatTime(item.todo.scheduled_start)}
                  {item.todo.scheduled_end &&
                    ` – ${formatTime(item.todo.scheduled_end)}`}
                </p>
              )}
            </div>
            <div className="flex items-center gap-1">
              {item.todo.deferred_count > 0 && (
                <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded mr-2">
                  deferred {item.todo.deferred_count}x
                </span>
              )}
              <button
                onClick={() => onUpdate(i, { action: "complete" })}
                className={`px-3 py-1 text-xs rounded-l-md border ${
                  item.action === "complete"
                    ? "bg-green-100 text-green-700 border-green-300"
                    : "bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100"
                }`}
              >
                Done
              </button>
              <button
                onClick={() => onUpdate(i, { action: "reschedule" })}
                className={`px-3 py-1 text-xs rounded-r-md border border-l-0 ${
                  item.action === "reschedule"
                    ? "bg-amber-100 text-amber-700 border-amber-300"
                    : "bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100"
                }`}
              >
                Reschedule
              </button>
            </div>
          </div>

          <textarea
            value={item.notes}
            onChange={(e) => onUpdate(i, { notes: e.target.value })}
            placeholder="Notes (optional)"
            rows={1}
            className="mt-3 w-full text-sm border border-gray-200 rounded px-3 py-1.5 placeholder-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-300 resize-none"
          />
        </div>
      ))}

      <button
        onClick={onContinue}
        className="w-full py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
      >
        Continue to Plan
      </button>
    </div>
  );
}

/* ── Step 2: Today's Plan ────────────────────────────────────────── */

function PlanStep({
  plan,
  approvedTodoIds,
  onToggle,
  regenerating,
  onRegenerate,
  feedback,
  onFeedbackChange,
  refining,
  onRefine,
  submitting,
  onSubmit,
  onBack,
}: {
  plan: StoredPlan | null;
  approvedTodoIds: Set<string>;
  onToggle: (todoId: string) => void;
  regenerating: boolean;
  onRegenerate: () => void;
  feedback: string;
  onFeedbackChange: (v: string) => void;
  refining: boolean;
  onRefine: () => void;
  submitting: boolean;
  onSubmit: () => void;
  onBack?: () => void;
}) {
  if (!plan) {
    return (
      <div className="space-y-4">
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 text-center">
          <p className="text-gray-600 font-medium">No plan generated yet</p>
          <p className="text-gray-400 text-sm mt-1">
            Generate a plan, or skip to finish the review
          </p>
          <div className="flex justify-center gap-3 mt-4">
            <button
              onClick={onRegenerate}
              disabled={regenerating}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              {regenerating ? "Generating..." : "Generate Plan"}
            </button>
            <button
              onClick={onSubmit}
              disabled={submitting}
              className="px-4 py-2 border border-gray-200 text-gray-600 text-sm rounded hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              {submitting ? "Finishing..." : "Skip & Finish"}
            </button>
          </div>
        </div>
        {onBack && (
          <button
            onClick={onBack}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Back to Review
          </button>
        )}
      </div>
    );
  }

  const proposal = plan.proposal;
  const existingEvents = proposal.existing_events ?? [];
  const planItems = proposal.plan_items ?? [];

  // Build unified timeline
  type TimelineEntry =
    | { kind: "existing"; title: string; start: string; end: string }
    | {
        kind: "proposed";
        todoId: string;
        todoTitle: string;
        title: string;
        start: string;
        end: string;
        duration: number;
        approved: boolean;
      };

  const timeline: TimelineEntry[] = [];

  for (const ev of existingEvents) {
    timeline.push({ kind: "existing", title: ev.title, start: ev.start, end: ev.end });
  }

  for (const item of planItems) {
    for (const task of item.tasks) {
      timeline.push({
        kind: "proposed",
        todoId: item.todo_id,
        todoTitle: item.todo_title ?? "",
        title: task.title,
        start: task.scheduled_start,
        end: task.scheduled_end,
        duration: task.estimated_duration_minutes,
        approved: approvedTodoIds.has(item.todo_id),
      });
    }
  }

  timeline.sort(
    (a, b) => new Date(a.start).getTime() - new Date(b.start).getTime()
  );

  const approvedCount = planItems.filter((i) =>
    approvedTodoIds.has(i.todo_id)
  ).length;

  return (
    <div className="space-y-4">
      {plan.spoken_summary && (
        <p className="text-sm text-gray-600 italic">{plan.spoken_summary}</p>
      )}

      {/* Timeline */}
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Proposed Plan
          </div>
          <div className="text-xs text-gray-400">
            {existingEvents.length > 0 &&
              `${existingEvents.length} existing · `}
            {approvedCount}/{planItems.length} approved
          </div>
        </div>

        {timeline.length === 0 ? (
          <p className="text-sm text-gray-400 py-4 text-center">
            No events or tasks for today
          </p>
        ) : (
          <div className="space-y-0.5">
            {timeline.map((entry, idx) => (
              <div
                key={idx}
                className={`flex items-start gap-3 py-2.5 border-l-2 pl-3 ${
                  entry.kind === "existing"
                    ? "border-l-gray-300"
                    : entry.approved
                      ? "border-l-indigo-400"
                      : "border-l-gray-200 opacity-50"
                }`}
              >
                {/* Checkbox for proposed items */}
                <div className="w-5 shrink-0 pt-0.5">
                  {entry.kind === "proposed" && (
                    <input
                      type="checkbox"
                      checked={entry.approved}
                      onChange={() => onToggle(entry.todoId)}
                      className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                  )}
                </div>

                {/* Time */}
                <div className="w-28 shrink-0 text-xs text-gray-500 pt-0.5">
                  {formatTime(entry.start)} – {formatTime(entry.end)}
                </div>

                {/* Title + badge */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-sm font-medium truncate ${
                        entry.kind === "existing"
                          ? "text-gray-500"
                          : "text-gray-800"
                      }`}
                    >
                      {entry.title}
                    </span>
                    <span
                      className={`shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded ${
                        entry.kind === "existing"
                          ? "bg-gray-100 text-gray-500"
                          : "bg-indigo-100 text-indigo-700"
                      }`}
                    >
                      {entry.kind === "existing" ? "Existing" : "New"}
                    </span>
                  </div>
                  {entry.kind === "proposed" && (
                    <div className="text-xs text-gray-400 mt-0.5">
                      {entry.todoTitle && `${entry.todoTitle} · `}
                      {entry.duration > 0 && formatDuration(entry.duration)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Feedback input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={feedback}
          onChange={(e) => onFeedbackChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !refining) onRefine();
          }}
          placeholder="Request changes (e.g., move gym to 4pm)..."
          disabled={refining}
          className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 placeholder-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-300 disabled:opacity-50"
        />
        <button
          onClick={onRefine}
          disabled={refining || !feedback.trim()}
          className="px-4 py-2 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50"
        >
          {refining ? "Updating..." : "Send"}
        </button>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={onRegenerate}
          disabled={regenerating || refining}
          className="px-4 py-2.5 text-sm border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
        >
          {regenerating ? "Regenerating..." : "Regenerate"}
        </button>
        <button
          onClick={onSubmit}
          disabled={submitting || refining}
          className="flex-1 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {submitting ? "Submitting..." : "Approve Plan"}
        </button>
      </div>

      {onBack && (
        <button
          onClick={onBack}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Back to Review
        </button>
      )}
    </div>
  );
}

/* ── Success View ────────────────────────────────────────────────��─ */

function SuccessView({
  result,
  plan,
}: {
  result: SubmitResult;
  plan: StoredPlan | null;
}) {
  const { review, plan: planResult } = result;
  return (
    <div className="space-y-4">
      <div className="bg-green-50 border border-green-200 rounded-lg p-5 text-center space-y-1">
        <p className="text-green-800 font-medium">All set for today!</p>
        <div className="text-green-700 text-sm">
          {(review.completed > 0 || review.rescheduled > 0) && (
            <p>
              {review.completed > 0 &&
                `${review.completed} task${review.completed !== 1 ? "s" : ""} completed`}
              {review.completed > 0 && review.rescheduled > 0 && ", "}
              {review.rescheduled > 0 &&
                `${review.rescheduled} rescheduled`}
            </p>
          )}
          {planResult.items_created > 0 && (
            <p>
              {planResult.items_created} item{planResult.items_created !== 1 ? "s" : ""}{" "}
              scheduled
              {planResult.events_created > 0 &&
                ` with ${planResult.events_created} calendar event${planResult.events_created !== 1 ? "s" : ""}`}
            </p>
          )}
        </div>
      </div>

      <HistoricalPlanView plan={plan} />
    </div>
  );
}
