const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;

/* =========================================
   ACCESS TOKEN
========================================= */

function setAccessToken(token: string | null) {
  accessToken = token;
}

/* =========================================
   AUTHENTICATED API REQUEST
========================================= */

export async function apiFetch(
  endpoint: string,
  options: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(options.headers);

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  let response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
    credentials: "include",
  });

  // Access token may have expired
  if (response.status === 401) {
    // Share refresh rotation across simultaneous requests and Strict Mode restoration.
    if (!(await restoreSession())) return response;
    headers.set("Authorization", `Bearer ${accessToken}`);

    response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers,
      credentials: "include",
    });
  }

  return response;
}

/* =========================================
   LOGIN
========================================= */

export type LoginData = {
  email: string;
  password: string;
};

export async function login(data: LoginData) {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",

    headers: {
      "Content-Type": "application/json",
    },

    credentials: "include",

    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error("Invalid email or password");
  }

  const result = await response.json();

  setAccessToken(result.access_token);

  return result;
}

/* =========================================
   REGISTER
========================================= */

export type RegisterData = {
  full_name: string;
  email: string;
  password: string;
};

export async function register(data: RegisterData) {
  const response = await fetch(`${API_URL}/auth/register`, {
    method: "POST",

    headers: {
      "Content-Type": "application/json",
    },

    credentials: "include",

    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorData = await response.json();

    throw new Error(
      typeof errorData.detail === "string"
        ? errorData.detail
        : "Unable to create account",
    );
  }

  return response.json();
}

/* =========================================
   LOGOUT
========================================= */

export async function logout() {
  const response = await fetch(`${API_URL}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });

  if (!response.ok) throw new Error("Could not sign out.");
  setAccessToken(null);
}

/* =========================================
   RESTORE SESSION
========================================= */

export function restoreSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_URL}/auth/refresh`, {
          method: "POST",
          credentials: "include",
        });
        if (!response.ok) {
          setAccessToken(null);
          return false;
        }
        const data = await response.json();
        setAccessToken(data.access_token);
        return true;
      } catch {
        setAccessToken(null);
        return false;
      }
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/* =========================================
   DOCUMENT TYPES
========================================= */

export type DocumentStatus = "UPLOADED" | "PROCESSING" | "READY" | "FAILED";

export interface DocumentItem {
  id: number;
  original_filename: string;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
  chunk_count: number;
}

export type DocumentUploadResponse = DocumentItem;

/* =========================================
   CHAT TYPES
========================================= */

export interface ChatSource {
  document_id: number;
  filename: string;
  page_number: number | null;
  chunk_index: number;
  similarity_score: number;
}

export interface ChatResponse {
  session_id: number;
  session: ChatSession;
  user_message: ChatMessageItem;
  assistant_message: ChatMessageItem;
  answer: string;
  sources: ChatSource[];
}

/* =========================================
   GET DOCUMENTS
========================================= */

export async function getDocuments(): Promise<DocumentItem[]> {
  const response = await apiFetch("/documents");

  if (!response.ok) {
    throw new Error("Failed to load documents.");
  }

  return response.json();
}

export async function getDocument(documentId: number): Promise<DocumentItem> {
  const response = await apiFetch(`/documents/${documentId}`);

  if (!response.ok) {
    throw new Error("Failed to load document.");
  }

  return response.json();
}

/* =========================================
   UPLOAD DOCUMENT
========================================= */

export async function uploadDocument(
  file: File,
): Promise<DocumentUploadResponse> {
  const formData = new FormData();

  formData.append("file", file);

  const response = await apiFetch("/documents/upload", {
    method: "POST",
    body: formData,
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      typeof data.detail === "string" ? data.detail : "Document upload failed.",
    );
  }

  return data;
}

/* =========================================
   DELETE DOCUMENT
========================================= */

export async function deleteDocument(documentId: number): Promise<void> {
  const response = await apiFetch(`/documents/${documentId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    let message = "Failed to delete document.";

    try {
      const data = await response.json();

      if (typeof data.detail === "string") {
        message = data.detail;
      }
    } catch {
      // DELETE may return no JSON body.
    }

    throw new Error(message);
  }
}

/* =========================================
   RAG CHAT
========================================= */

export async function askQuestion(
  query: string,
  topK = 5,
  sessionId?: number,
): Promise<ChatResponse> {
  const response = await apiFetch("/chat/query", {
    method: "POST",

    headers: {
      "Content-Type": "application/json",
    },

    body: JSON.stringify({
      query,
      top_k: topK,
      session_id: sessionId,
    }),
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Failed to generate answer.",
    );
  }

  return data;
}

export async function askQuestionStream(
  query: string,
  topK = 5,
  sessionId: number,
  onDelta: (content: string) => void,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await apiFetch("/chat/query/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ query, top_k: topK, session_id: sessionId }),
    signal,
  });
  if (!response.ok || !response.body) throw new Error("Failed to generate answer.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let complete: ChatResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = frame.match(/^event: (.+)$/m)?.[1];
      const data = frame.match(/^data: (.+)$/m)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data);
      if (event === "delta") onDelta(payload.content);
      if (event === "complete") complete = payload as ChatResponse;
    }
    if (done) break;
  }
  if (!complete) throw new Error("The answer stream ended unexpectedly.");
  return complete;
}
export interface ChatSession {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}
export interface ChatMessageItem {
  id: number;
  role: "USER" | "ASSISTANT";
  content: string;
  sources: ChatSource[];
  created_at: string;
}
export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessageItem[];
}
export async function getChatSessions(): Promise<ChatSession[]> {
  const response = await apiFetch("/chat/sessions");
  if (!response.ok) throw new Error("Could not load conversations.");
  return response.json();
}
export async function createChatSession(): Promise<ChatSession> {
  const response = await apiFetch("/chat/sessions", { method: "POST" });
  if (!response.ok) throw new Error("Could not create a conversation.");
  return response.json();
}
export async function getChatSession(id: number): Promise<ChatSessionDetail> {
  const response = await apiFetch(`/chat/sessions/${id}`);
  if (!response.ok) throw new Error("Could not load the conversation.");
  return response.json();
}
export async function deleteChatSession(id: number): Promise<void> {
  const response = await apiFetch(`/chat/sessions/${id}`, { method: "DELETE" });
  if (!response.ok) throw new Error("Could not delete the conversation.");
}
