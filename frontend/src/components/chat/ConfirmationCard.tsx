/**
 * ConfirmationCard -- Approve/Reject UI for HIGH_STAKES agent actions.
 *
 * Shown inline below an AssistantMessage when the agent's response includes
 * a confirmation_required field. Clicking Approve calls confirmAction() in
 * the useChat hook, which re-sends the original message with the confirmation_id.
 * Clicking Reject sends a cancellation message.
 */
import { useState } from "react";
import type { ConfirmationRequired } from "../../types/chat";

interface Props {
  confirmation: ConfirmationRequired;
  onConfirm: (confirmationId: string) => void;
  onReject: () => void;
  disabled?: boolean;
}

export default function ConfirmationCard({
  confirmation,
  onConfirm,
  onReject,
  disabled,
}: Props) {
  const [acted, setActed] = useState(false);

  const handleConfirm = () => {
    setActed(true);
    onConfirm(confirmation.confirmation_id);
  };

  const handleReject = () => {
    setActed(true);
    onReject();
  };

  return (
    <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-4">
      <p className="text-sm font-medium text-amber-800 mb-1">
        Confirmation Required
      </p>
      <p className="text-sm text-amber-700 mb-3">{confirmation.description}</p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={acted || disabled}
          className="rounded-lg bg-green-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Approve
        </button>
        <button
          type="button"
          onClick={handleReject}
          disabled={acted || disabled}
          className="rounded-lg bg-red-500 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
