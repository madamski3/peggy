/**
 * AssistantMessage -- renders a single agent response.
 *
 * Shows the spoken_summary text, plus:
 *   - Collapsible action list (if the agent called tools)
 *   - Confirmation card (if a HIGH_STAKES tool needs approval)
 *   - Follow-up suggestion chips (only on the most recent message)
 */
import { useState } from "react";
import type { ChatMessage } from "../../types/chat";
import ConfirmationCard from "./ConfirmationCard";
import FollowUpChips from "./FollowUpChips";

interface Props {
  message: ChatMessage;
  onFollowUp: (text: string) => void;
  onConfirm: (confirmationId: string) => void;
  onReject: () => void;
  isLatest: boolean;
  isLoading?: boolean;
}

export default function AssistantMessage({
  message,
  onFollowUp,
  onConfirm,
  onReject,
  isLatest,
  isLoading,
}: Props) {
  const [showActions, setShowActions] = useState(false);
  const response = message.response;
  const actions = response?.actions_taken ?? [];

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%]">
        {/* Main spoken summary */}
        <div className="rounded-2xl rounded-bl-md bg-white border border-gray-200 px-4 py-3 text-sm text-gray-800 whitespace-pre-wrap shadow-sm">
          {message.content}
        </div>

        {/* Actions taken (collapsible) */}
        {actions.length > 0 && (
          <div className="mt-2">
            <button
              type="button"
              onClick={() => setShowActions(!showActions)}
              className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              {showActions ? "Hide" : "Show"} {actions.length} action
              {actions.length !== 1 ? "s" : ""}
            </button>
            {showActions && (
              <div className="mt-1 space-y-1">
                {actions.map((action, idx) => (
                  <div
                    key={idx}
                    className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2 text-xs text-gray-600"
                  >
                    <span className="font-medium text-gray-700">
                      {action.tool_name}
                    </span>
                    <span className="mx-1.5 text-gray-300">|</span>
                    {action.result_summary}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Confirmation card */}
        {response?.confirmation_required && (
          <ConfirmationCard
            confirmation={response.confirmation_required}
            onConfirm={onConfirm}
            onReject={onReject}
            disabled={isLoading}
          />
        )}

        {/* Follow-up suggestions (only on the latest message) */}
        {isLatest && response?.follow_up_suggestions && (
          <FollowUpChips
            suggestions={response.follow_up_suggestions}
            onSelect={onFollowUp}
            disabled={isLoading}
          />
        )}
      </div>
    </div>
  );
}
