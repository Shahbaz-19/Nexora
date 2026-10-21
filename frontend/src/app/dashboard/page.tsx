"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ChatInterface from "@/components/dashboard/ChatInterface";
import DashboardSidebar from "@/components/dashboard/DashboardSidebar";
import KnowledgeBasePanel from "@/components/dashboard/KnowledgeBasePanel";
import { useAuth } from "@/context/AuthContext";
import {
  askQuestionStream,
  createChatSession,
  deleteChatSession,
  getChatSession,
  getChatSessions,
  type ChatMessageItem,
  type ChatSession,
} from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const { user, logout, loading } = useAuth();
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);
  if (loading)
    return (
      <main className="grid h-dvh place-items-center" role="status">
        Restoring your session…
      </main>
    );
  if (!user) return null;
  return (
    <Dashboard
      key={user.id}
      name={user.full_name}
      onLogout={async () => {
        await logout();
        router.replace("/login");
      }}
    />
  );
}

function Dashboard({
  name,
  onLogout,
}: {
  name: string;
  onLogout: () => Promise<void>;
}) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [historyUnavailable, setHistoryUnavailable] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [listError, setListError] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [view, setView] = useState<"chat" | "knowledge">("chat");
  const [draft, setDraft] = useState("");
  const [focusVersion, setFocusVersion] = useState(0);
  const requestVersion = useRef(0);
  const mutation = useRef(false);
  const closeDrawer = useCallback(() => setDrawer(false), []);

  async function loadSessions() {
    setListLoading(true);
    setListError("");
    try {
      setSessions(await getChatSessions());
    } catch {
      setListError("Could not load your conversations.");
    } finally {
      setListLoading(false);
    }
  }
  useEffect(() => {
    let cancelled = false;
    getChatSessions()
      .then((data) => {
        if (!cancelled) setSessions(data);
      })
      .catch(() => {
        if (!cancelled) setListError("Could not load your conversations.");
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function newChat() {
    if (mutation.current) return;
    requestVersion.current++;
    setFocusVersion(value => value + 1);
    setActiveId(null);
    setMessages([]);
    setDraft("");
    setError("");
    setHistoryLoading(false);
    setHistoryUnavailable(false);
    setDrawer(false);
    setView("chat");
  }
  async function selectSession(id: number) {
    if (mutation.current) return;
    const version = ++requestVersion.current;
    setActiveId(id);
    setMessages([]);
    setDraft("");
    setError("");
    setHistoryLoading(true);
    setHistoryUnavailable(false);
    setDrawer(false);
    setView("chat");
    try {
      const detail = await getChatSession(id);
      if (version === requestVersion.current) setMessages(detail.messages);
    } catch {
      if (version === requestVersion.current) {
        setHistoryUnavailable(true);
        setError("Could not load this conversation. Select it again to retry.");
      }
    } finally {
      if (version === requestVersion.current) setHistoryLoading(false);
    }
  }
  async function removeSession(id: number) {
    if (mutation.current) return;
    mutation.current = true;
    setBusy(true);
    setError("");
    try {
      await deleteChatSession(id);
      setSessions((current) => current.filter((session) => session.id !== id));
      if (activeId === id) {
        requestVersion.current++;
        setActiveId(null);
        setMessages([]);
        setDraft("");
        setHistoryLoading(false);
        setHistoryUnavailable(false);
      }
    } catch {
      setError("Could not delete the conversation. Please try again.");
    } finally {
      mutation.current = false;
      setBusy(false);
    }
  }
  async function send() {
    const query = draft.trim();
    if (
      !query ||
      mutation.current ||
      historyLoading ||
      historyUnavailable ||
      listLoading
    )
      return;
    mutation.current = true;
    setSending(true);
    setError("");
    setDraft("");
    const optimistic: ChatMessageItem = {
      id: -1,
      role: "USER",
      content: query,
      sources: [],
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimistic]);
    let id = activeId;
    try {
      if (id === null) {
        const session = await createChatSession();
        id = session.id;
        setActiveId(id);
        setSessions((current) => [{ ...session, title: query }, ...current]);
      }
      let streamed = "";
      const result = await askQuestionStream(query, 5, id, (content) => {
        streamed += content;
        setMessages((current) => [
          ...current.filter((message) => message.id !== -1 && message.id !== -2),
          optimistic,
          {
            id: -2,
            role: "ASSISTANT",
            content: streamed,
            sources: [],
            created_at: new Date().toISOString(),
          },
        ]);
      });
      setMessages((current) => [
        ...current.filter((message) => message.id !== -1 && message.id !== -2),
        result.user_message,
        result.assistant_message,
      ]);
      setSessions((current) => [
        result.session,
        ...current.filter((session) => session.id !== id),
      ]);
    } catch {
      // Reconcile after an ambiguous network failure before offering a retry.
      try {
        const detail = id === null ? null : await getChatSession(id);
        if (detail) {
          setMessages(detail.messages);
          setSessions((current) => [
            detail,
            ...current.filter((session) => session.id !== id),
          ]);
        } else
          setMessages((current) =>
            current.filter((message) => message.id !== -1 && message.id !== -2),
          );
        const last = detail?.messages.at(-2);
        if (
          last?.role === "USER" &&
          last.content === query &&
          detail!.messages.length > messages.length
        ) {
          setError(
            "The answer was saved; your connection briefly interrupted.",
          );
        } else {
          setDraft(query);
          setError("Could not send your question. Please try again.");
        }
      } catch {
        setMessages((current) =>
          current.filter((message) => message.id !== -1 && message.id !== -2),
        );
        setHistoryUnavailable(true);
        setDraft(query);
        setError(
          "Connection lost. Reload this conversation before retrying to check whether your answer was saved.",
        );
      }
    } finally {
      mutation.current = false;
      setSending(false);
    }
  }
  return (
    <main className="dashboard-shell">
      <DashboardSidebar
        sessions={sessions}
        activeId={activeId}
        activeView={view}
        loading={listLoading}
        error={listError}
        disabled={sending || busy}
        open={drawer}
        name={name}
        onClose={closeDrawer}
        onRetry={loadSessions}
        onNew={newChat}
        onSelect={selectSession}
        onKnowledgeBase={() => {
          if (mutation.current) return;
          setView("knowledge");
          setDrawer(false);
        }}
        onDelete={removeSession}
        onLogout={async () => {
          if (mutation.current) return;
          mutation.current = true;
          setBusy(true);
          try {
            await onLogout();
          } catch {
            setError("Could not sign out. Please try again.");
          } finally {
            mutation.current = false;
            setBusy(false);
          }
        }}
      />
      {view === "chat" ? (
        <ChatInterface
          focusVersion={focusVersion}
          messages={messages}
          loading={historyLoading}
          sending={sending}
          disabled={busy || historyUnavailable || listLoading}
          error={error}
          draft={draft}
          onDraft={setDraft}
          onSend={send}
          onMenu={() => setDrawer(true)}
          title={
            sessions.find((session) => session.id === activeId)?.title ??
            "New chat"
          }
        />
      ) : (
        <KnowledgeBasePanel onMenu={() => setDrawer(true)} />
      )}
    </main>
  );
}
