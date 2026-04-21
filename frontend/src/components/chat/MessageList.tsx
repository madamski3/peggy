/**
 * MessageList -- renders the scrollable message history.
 *
 * Handles three states:
 *   1. Empty (no messages) -- shows a welcome screen with suggestion chips
 *   2. Messages present -- renders UserMessage and AssistantMessage components
 *   3. Loading / Error -- shows a status message or bouncing dot indicator
 *
 * Auto-scrolls to the bottom on new messages.
 */
import { useEffect, useRef } from "react";
import type { ChatMessage, TurnPlan } from "../../types/chat";
import UserMessage from "./UserMessage";
import AssistantMessage from "./AssistantMessage";
import PlanProgress from "./PlanProgress";

interface Props {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  statusMessage: string | null;
  activePlan: TurnPlan | null;
  activeStepIndex: number | null;
  activeStepText: string | null;
  onFollowUp: (text: string) => void;
  onConfirm: (confirmationId: string) => void;
  onReject: () => void;
}

const WELCOME_SUGGESTIONS = [
  "Plan my day",
  "What's on my todo list?",
  "Any important emails?",
  "Remind me to call the vet at 3pm",
];

function relativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function MessageList({
  messages,
  isLoading,
  error,
  statusMessage,
  activePlan,
  activeStepIndex,
  activeStepText,
  onFollowUp,
  onConfirm,
  onReject,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages or loading state change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isLoading, statusMessage]);

  // Empty state
  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-4">
        <h2 className="text-xl font-semibold text-gray-700 mb-1">
          Good {new Date().getHours() < 12 ? "morning" : new Date().getHours() < 17 ? "afternoon" : "evening"}
        </h2>
        <p className="text-sm text-gray-400 mb-8 max-w-sm">
          How can I help you today?
        </p>
        <div className="flex flex-wrap justify-center gap-2 max-w-lg">
          {WELCOME_SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onFollowUp(s)}
              className="rounded-full border border-gray-200 bg-white px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 hover:border-gray-400 shadow-sm transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    );
  }

  const lastAssistantIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") return i;
    }
    return -1;
  })();

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="max-w-4xl mx-auto space-y-4">
        {messages.map((msg, i) => (
          <div key={msg.id}>
            {msg.role === "user" ? (
              <UserMessage message={msg} />
            ) : (
              <AssistantMessage
                message={msg}
                onFollowUp={onFollowUp}
                onConfirm={onConfirm}
                onReject={onReject}
                isLatest={i === lastAssistantIdx}
                isLoading={isLoading}
              />
            )}
            <div className="text-[10px] text-gray-300 mt-1 px-1">
              {relativeTime(msg.timestamp)}
            </div>
          </div>
        ))}

        {/* Plan progress (steps check off as the agent works through them) */}
        {isLoading && activePlan && (activePlan.goal || activePlan.steps.length > 0) && (
          <div className="flex justify-start">
            <div className="max-w-xl w-full">
              <PlanProgress
                plan={activePlan}
                activeStepIndex={activeStepIndex}
                activeStepText={activeStepText}
              />
            </div>
          </div>
        )}

        {/* Loading indicator with status message */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md bg-white border-l-[3px] border-l-indigo-400 border border-gray-200 px-4 py-3 shadow-sm">
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-1.5">
                  <span className="block w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce [animation-delay:0ms]" />
                  <span className="block w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce [animation-delay:150ms]" />
                  <span className="block w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce [animation-delay:300ms]" />
                </span>
                {statusMessage && (
                  <span className="text-sm text-gray-500 animate-fade-in">
                    {statusMessage}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
              Something went wrong. Please try again.
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
