import ReactMarkdown from "react-markdown";
import type { ChatMessageItem } from "@/lib/api";
import SourceCard from "./SourceCard";
import NexoraLogo from "@/components/brand/NexoraLogo";

export default function ChatMessage({ message }: { message: ChatMessageItem }) {
  if (message.role === "USER")
    return (
      <article className="user-message" aria-label="Your message">
        <div>{message.content}</div>
      </article>
    );
  return (
    <article className="assistant-message" aria-label="Assistant message">
      <div className="assistant-label">
        <NexoraLogo size={26} decorative /> Nexora
      </div>
      <div className="markdown">
        <ReactMarkdown
          skipHtml
          components={{
            img: () => null,
            a: ({ children, href }) => (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ),
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>
      {message.sources.length > 0 && (
        <section className="sources" aria-label="Sources">
          <h3>Sources</h3>
          <div className="source-grid">
            {message.sources.map((source, index) => (
              <SourceCard
                key={`${source.document_id}-${source.chunk_index}-${index}`}
                source={source}
              />
            ))}
          </div>
        </section>
      )}
    </article>
  );
}
