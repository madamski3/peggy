export interface ChatRequest {
  message: string;
  session_id?: string;
  confirmation_id?: string;
}

export interface ActionTaken {
  tool_name: string;
  tool_args: Record<string, unknown>;
  result_summary: string;
}

export interface ConfirmationRequired {
  confirmation_id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  description: string;
}

export interface ChatResponse {
  spoken_summary: string;
  structured_payload?: Record<string, unknown> | null;
  actions_taken: ActionTaken[];
  confirmation_required?: ConfirmationRequired | null;
  follow_up_suggestions: string[];
  session_id: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  // Only present on assistant messages
  response?: ChatResponse;
}
