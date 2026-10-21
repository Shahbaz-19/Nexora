"use client";

import { useEffect, useRef } from "react";
import type { ChatSession } from "@/lib/api";
import NexoraLogo from "@/components/brand/NexoraLogo";

interface Props {
  sessions: ChatSession[];
  activeId: number | null;
  activeView: "chat" | "knowledge";
  loading: boolean;
  error: string;
  disabled: boolean;
  open: boolean;
  name: string;
  onClose: () => void;
  onRetry: () => void;
  onNew: () => void;
  onSelect: (id: number) => void;
  onKnowledgeBase: () => void;
  onDelete: (id: number) => void;
  onLogout: () => void;
}
export default function DashboardSidebar(props: Props) {
  const { open, onClose } = props;
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLButtonElement>("button")?.focus();
    function trap(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab") return;
      const items = Array.from(
        panel.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled), summary",
        ) ?? [],
      ).filter((item) => item.getClientRects().length > 0);
      const first = items[0],
        last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, [open, onClose]);
  return (
    <>
      {props.open && (
        <button
          className="drawer-backdrop"
          aria-label="Close navigation"
          onClick={props.onClose}
        />
      )}
      <aside
        ref={panel}
        className={`sidebar ${props.open ? "is-open" : ""}`}
        aria-label="Chat navigation"
      >
        <div className="brand">
          <NexoraLogo size={38} />
          <div>
            <strong>Nexora</strong>
            <span>Intelligence, connected.</span>
          </div>
          <button
            className="icon-button drawer-close"
            onClick={props.onClose}
            aria-label="Close navigation"
          >
            ×
          </button>
        </div>
        <button
          className="new-chat"
          onClick={props.onNew}
          disabled={props.disabled}
        >
          <span aria-hidden="true">+</span> New Chat
        </button>
        <button
          className={`knowledge-nav ${props.activeView === "knowledge" ? "active" : ""}`}
          onClick={props.onKnowledgeBase}
          disabled={props.disabled}
        >
          <span aria-hidden="true">KB</span> Knowledge Base
        </button>
        <div className="recent-label">Recent Chats</div>
        <nav className="conversation-list" aria-label="Recent conversations">
          {props.loading ? (
            <p className="sidebar-note" role="status">
              Loading conversations…
            </p>
          ) : props.error ? (
            <div className="sidebar-note" role="alert">
              {props.error}
              <button className="text-button" onClick={props.onRetry}>
                Try again
              </button>
            </div>
          ) : props.sessions.length === 0 ? (
            <div className="history-empty">
              <span aria-hidden="true">&#9671;</span>
              <strong>A fresh start</strong>
              <p>
                Your conversations will appear here after your first question.
              </p>
            </div>
          ) : (
            props.sessions.map((session) => (
              <div
                className={`conversation-row ${props.activeId === session.id ? "active" : ""}`}
                key={session.id}
              >
                <button
                  className="conversation-title"
                  title={session.title}
                  aria-current={
                    props.activeId === session.id ? "page" : undefined
                  }
                  disabled={props.disabled}
                  onClick={() => props.onSelect(session.id)}
                >
                  {session.title}
                </button>
                <details className="conversation-menu">
                  <summary aria-label={`Actions for ${session.title}`}>
                    ···
                  </summary>
                  <button
                    disabled={props.disabled}
                    onClick={(event) => {
                      event.currentTarget
                        .closest("details")
                        ?.removeAttribute("open");
                      props.onDelete(session.id);
                    }}
                  >
                    Delete conversation
                  </button>
                </details>
              </div>
            ))
          )}
        </nav>
        <div className="sidebar-footer">
          <div className="user-identity">
            <span>{props.name.slice(0, 1).toUpperCase()}</span>
            <p title={props.name}>{props.name}</p>
          </div>
          <button disabled={props.disabled} onClick={props.onLogout}>
            Sign out <span aria-hidden="true">&#8599;</span>
          </button>
        </div>
      </aside>
    </>
  );
}
