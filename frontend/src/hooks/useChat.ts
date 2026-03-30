/**
 * useChat -- the central state manager for the chat interface.
 *
 * Manages the message list, session ID, loading state, and error state.
 * Provides four actions:
 *   - sendMessage(text) -- POST to /api/chat/, append user + assistant messages
 *   - confirmAction(id) -- re-send the last message with a confirmation_id to
 *     approve a HIGH_STAKES tool call
 *   - rejectAction()    -- send "Never mind, cancel that." as a regular message
 *   - startNewChat()    -- reset all state for a fresh conversation
 *
 * The session_id is set from the first API response and sent on all subsequent
 * requests, giving the backend conversation continuity.
 */
import { useState, useCallback, useRef } from "react";
import { generateId } from "../utils/id";
import type { ChatMessage, ChatRequest, ChatResponse } from "../types/chat";

interface UseChatReturn {
  messages: ChatMessage[];
  sessionId: string | null;
  isLoading: boolean;
  error: string | null;
  sendMessage: (text: string) => Promise<void>;
  confirmAction: (confirmationId: string) => Promise<void>;
  rejectAction: () => Promise<void>;
  startNewChat: () => void;
}

async function postChat(body: ChatRequest): Promise<ChatResponse> {
  const res = await fetch("/api/chat/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Request failed (${res.status})`);
  }
  return res.json();
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track the last user message for confirmation re-sends
  const lastUserMessage = useRef<string>("");

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      lastUserMessage.current = trimmed;
      setError(null);

      // Append user message
      const userMsg: ChatMessage = {
        id: generateId(),
        role: "user",
        content: trimmed,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      try {
        const body: ChatRequest = { message: trimmed };
        if (sessionId) body.session_id = sessionId;

        const response = await postChat(body);
        setSessionId(response.session_id);

        const assistantMsg: ChatMessage = {
          id: generateId(),
          role: "assistant",
          content: response.spoken_summary,
          timestamp: new Date(),
          response,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Something went wrong";
        setError(msg);
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId],
  );

  const confirmAction = useCallback(
    async (confirmationId: string) => {
      setError(null);
      setIsLoading(true);

      try {
        const body: ChatRequest = {
          message: lastUserMessage.current,
          confirmation_id: confirmationId,
        };
        if (sessionId) body.session_id = sessionId;

        const response = await postChat(body);
        setSessionId(response.session_id);

        const assistantMsg: ChatMessage = {
          id: generateId(),
          role: "assistant",
          content: response.spoken_summary,
          timestamp: new Date(),
          response,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Something went wrong";
        setError(msg);
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId],
  );

  const rejectAction = useCallback(async () => {
    await sendMessage("Never mind, cancel that.");
  }, [sendMessage]);

  const startNewChat = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    setError(null);
    setIsLoading(false);
    lastUserMessage.current = "";
  }, []);

  return {
    messages,
    sessionId,
    isLoading,
    error,
    sendMessage,
    confirmAction,
    rejectAction,
    startNewChat,
  };
}
