"use client";

import { useEffect, useRef } from "react";
import type { ChatMessageItem } from "@/lib/api";
import ChatMessage from "./ChatMessage";
import ChatComposer from "./ChatComposer";
import NexoraLogo from "@/components/brand/NexoraLogo";

interface Props {
  focusVersion: number;
  messages: ChatMessageItem[];
  loading: boolean;
  sending: boolean;
  disabled: boolean;
  error: string;
  draft: string;
  title: string;
  onDraft: (value: string) => void;
  onSend: () => Promise<void>;
  onMenu: () => void;
}
export default function ChatInterface(props: Props) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
      block: "end",
    });
  }, [props.messages, props.sending, props.loading]);
  return (
    <section className="chat-main" aria-label="Conversation">
      <header className="chat-header">
        <button
          className="icon-button menu-toggle"
          aria-label="Open navigation"
          onClick={props.onMenu}
        >
          &#9776;
        </button>
        <h1 title={props.title}>{props.title}</h1>
      </header>
      <div className="chat-scroll" aria-busy={props.loading}>
        {props.loading ? (
          <div className="chat-empty" role="status">
            <NexoraLogo size={42} decorative />
            <span className="loading-label">Loading conversation…</span>
          </div>
        ) : props.messages.length === 0 ? (
          <div className="chat-empty">
            <NexoraLogo size={52} decorative />
            <p className="eyebrow">INTELLIGENCE, CONNECTED.</p>
            <h2>What would you like to know?</h2>
            <p>Ask questions across your connected knowledge base.</p>
            <p className="empty-hint">Add a document with + to get started.</p>
          </div>
        ) : (
          <div className="message-list">
            {props.messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
            {props.sending && (
              <p className="thinking" role="status">
                <span className="status-dot" /> Thinking…
              </p>
            )}
          </div>
        )}
        <div ref={end} />
      </div>
      <div className="composer-footer">
        {props.error && (
          <p className="chat-error" role="alert">
            {props.error}
          </p>
        )}
        <ChatComposer
          focusVersion={props.focusVersion}
          draft={props.draft}
          onDraft={props.onDraft}
          onSend={props.onSend}
          disabled={props.disabled || props.loading || props.sending}
          sending={props.sending}
        />
      </div>
    </section>
  );
}
