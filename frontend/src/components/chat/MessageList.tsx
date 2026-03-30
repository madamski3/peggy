/**
 * MessageList -- renders the scrollable message history.
 *
 * Handles three states:
 *   1. Empty (no messages) -- shows a welcome screen with suggestion chips
 *   2. Messages present -- renders UserMessage and AssistantMessage components
 *   3. Loading / Error -- shows a bouncing dot indicator or error banner
 *
 * Auto-scrolls to the bottom on new messages.
 */
import { useEffect, useRef } from "react";
import type { ChatMessage } from "../../types/chat";
import UserMessage from "./UserMessage";
import AssistantMessage from "./AssistantMessage";

interface Props {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  onFollowUp: (text: string) => void;
  onConfirm: (confirmationId: string) => void;
  onReject: () => void;
}

const WELCOME_SUGGESTIONS = [
  "Plan my day",
  "What's on my todo list?",
  "Tell me about myself",
];

export default function MessageList({
  messages,
  isLoading,
  error,
  onFollowUp,
  onConfirm,
  onReject,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages or loading state change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isLoading]);

  // Empty state
  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-4">
        <div className="text-4xl mb-3">👋</div>
        <h2 className="text-lg font-medium text-gray-700 mb-1">
          Hi! I'm your assistant.
        </h2>
        <p className="text-sm text-gray-400 mb-6 max-w-sm">
          Ask me to plan your day, manage your todos, look things up, or
          anything else.
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          {WELCOME_SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onFollowUp(s)}
              className="rounded-full border border-gray-300 bg-white px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 hover:border-gray-400 transition-colors"
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
        {messages.map((msg, i) =>
          msg.role === "user" ? (
            <UserMessage key={msg.id} message={msg} />
          ) : (
            <AssistantMessage
              key={msg.id}
              message={msg}
              onFollowUp={onFollowUp}
              onConfirm={onConfirm}
              onReject={onReject}
              isLatest={i === lastAssistantIdx}
              isLoading={isLoading}
            />
          ),
        )}

        {/* Loading indicator */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md bg-white border border-gray-200 px-4 py-3 shadow-sm">
              <div className="flex items-center gap-1.5">
                <span className="block w-2 h-2 rounded-full bg-gray-400 animate-bounce [animation-delay:0ms]" />
                <span className="block w-2 h-2 rounded-full bg-gray-400 animate-bounce [animation-delay:150ms]" />
                <span className="block w-2 h-2 rounded-full bg-gray-400 animate-bounce [animation-delay:300ms]" />
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
