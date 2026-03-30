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
    sendMessage,
    confirmAction,
    rejectAction,
    startNewChat,
  } = useChat();

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      <MessageList
        messages={messages}
        isLoading={isLoading}
        error={error}
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
