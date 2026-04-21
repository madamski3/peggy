/**
 * ChatPage -- the main chat interface, composed of MessageList + InputBar.
 *
 * This is the default route ("/"). It wires the useChat hook to the
 * presentational components. All chat state lives in the hook; this
 * component is purely a layout shell.
 */
import { useChat } from "../../hooks/useChat";
import MessageList from "./MessageList";
import InputBar from "./InputBar";

export default function ChatPage() {
  const {
    messages,
    isLoading,
    error,
    statusMessage,
    activePlan,
    activeStepIndex,
    activeStepText,
    sendMessage,
    confirmAction,
    rejectAction,
    startNewChat,
  } = useChat();

  return (
    <div className="flex flex-col h-screen">
      {/* Session header */}
      {messages.length > 0 && (
        <div className="border-b border-gray-100 bg-white/80 backdrop-blur-sm px-4 py-1.5">
          <div className="max-w-4xl mx-auto flex items-center justify-between">
            <span className="text-xs text-gray-400">
              {messages.length} message{messages.length !== 1 ? "s" : ""} in this conversation
            </span>
          </div>
        </div>
      )}
      <MessageList
        messages={messages}
        isLoading={isLoading}
        error={error}
        statusMessage={statusMessage}
        activePlan={activePlan}
        activeStepIndex={activeStepIndex}
        activeStepText={activeStepText}
        onFollowUp={sendMessage}
        onConfirm={confirmAction}
        onReject={rejectAction}
      />
      <InputBar
        onSend={sendMessage}
        onNewChat={startNewChat}
        disabled={isLoading}
      />
    </div>
  );
}
