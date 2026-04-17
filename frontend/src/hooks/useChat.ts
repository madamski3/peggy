/**
 * useChat -- the central state manager for the chat interface.
 *
 * Manages the message list, session ID, loading state, and error state.
 * Provides four actions:
 *   - sendMessage(text) -- streams via SSE to /api/chat/stream, with
 *     fallback to POST /api/chat/ on failure
 *   - confirmAction(id) -- re-send the last message with a confirmation_id to
 *     approve a HIGH_STAKES tool call
 *   - rejectAction()    -- send "Never mind, cancel that." as a regular message
 *   - startNewChat()    -- reset all state for a fresh conversation
 *
 * The session_id is set from the first API response and sent on all subsequent
 * requests, giving the backend conversation continuity.
 *
 * Status messages are exposed via statusMessage for real-time progress
 * display during the agent's tool-use loop.
 */
import { useState, useCallback, useRef } from "react";
import { generateId } from "../utils/id";
import type { ChatMessage, ChatRequest, ChatResponse } from "../types/chat";

interface UseChatReturn {
  messages: ChatMessage[];
  sessionId: string | null;
  isLoading: boolean;
  error: string | null;
  statusMessage: string | null;
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

/**
 * Send a chat request via SSE and yield status updates.
 * Returns the final ChatResponse or throws on error.
 */
async function streamChat(
  body: ChatRequest,
  onStatus: (message: string) => void,
): Promise<ChatResponse> {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Request failed (${res.status})`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let result: ChatResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Process complete SSE messages (double newline delimited)
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const lines = part.trim().split("\n");
      let eventType = "message";
      let data = "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7);
        } else if (line.startsWith("data: ")) {
          data = line.slice(6);
        }
      }

      if (!data) continue;

      try {
        const parsed = JSON.parse(data);

        if (eventType === "status") {
          onStatus(parsed.message);
        } else if (eventType === "complete") {
          result = parsed as ChatResponse;
        } else if (eventType === "error") {
          throw new Error(parsed.error || "Stream error");
        }
      } catch (e) {
        if (e instanceof SyntaxError) continue; // skip malformed JSON
        throw e;
      }
    }
  }

  if (!result) throw new Error("Stream ended without a response");
  return result;
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Track the last user message for confirmation re-sends
  const lastUserMessage = useRef<string>("");

  const handleResponse = useCallback((response: ChatResponse) => {
    setSessionId(response.session_id);

    const assistantMsg: ChatMessage = {
      id: generateId(),
      role: "assistant",
      content: response.spoken_summary,
      timestamp: new Date(),
      response,
    };
    setMessages((prev) => [...prev, assistantMsg]);
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      lastUserMessage.current = trimmed;
      setError(null);
      setStatusMessage(null);

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

        // Try SSE streaming first, fall back to standard POST
        try {
          const response = await streamChat(body, setStatusMessage);
          handleResponse(response);
        } catch {
          // SSE failed — fall back to non-streaming
          setStatusMessage(null);
          const response = await postChat(body);
          handleResponse(response);
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Something went wrong";
        setError(msg);
      } finally {
        setIsLoading(false);
        setStatusMessage(null);
      }
    },
    [sessionId, handleResponse],
  );

  const confirmAction = useCallback(
    async (confirmationId: string) => {
      setError(null);
      setStatusMessage(null);
      setIsLoading(true);

      try {
        const body: ChatRequest = {
          message: lastUserMessage.current,
          confirmation_id: confirmationId,
        };
        if (sessionId) body.session_id = sessionId;

        // Confirmations use standard POST (fast, no streaming needed)
        const response = await postChat(body);
        handleResponse(response);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Something went wrong";
        setError(msg);
      } finally {
        setIsLoading(false);
        setStatusMessage(null);
      }
    },
    [sessionId, handleResponse],
  );

  const rejectAction = useCallback(async () => {
    await sendMessage("Never mind, cancel that.");
  }, [sendMessage]);

  const startNewChat = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    setError(null);
    setIsLoading(false);
    setStatusMessage(null);
    lastUserMessage.current = "";
  }, []);

  return {
    messages,
    sessionId,
    isLoading,
    error,
    statusMessage,
    sendMessage,
    confirmAction,
    rejectAction,
    startNewChat,
  };
}
