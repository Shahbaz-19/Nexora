"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { uploadDocument } from "@/lib/api";
import FileChip from "./FileChip";

export default function ChatComposer({
  focusVersion,
  draft,
  onDraft,
  onSend,
  disabled,
  sending,
}: {
  focusVersion: number;
  draft: string;
  onDraft: (value: string) => void;
  onSend: () => Promise<void>;
  disabled: boolean;
  sending: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const uploadBusy = useRef(false);
  const [uploading, setUploading] = useState(false);
  const [files, setFiles] = useState<
    { id: number; name: string; description: string }[]
  >([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (textarea.current) {
      textarea.current.style.height = "auto";
      textarea.current.style.height = `${Math.min(textarea.current.scrollHeight, 160)}px`;
    }
  }, [draft]);
  useEffect(() => {
    if (!disabled) textarea.current?.focus();
  }, [disabled, focusVersion]);
  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || uploadBusy.current) return;
    setError("");
    if (!/\.(pdf|txt|md)$/i.test(file.name)) {
      setError("Choose a PDF, TXT, or Markdown file.");
      return;
    }
    if (file.size === 0 || file.size > 10 * 1024 * 1024) {
      setError("Choose a nonempty file up to 10 MB.");
      return;
    }
    uploadBusy.current = true;
    setUploading(true);
    try {
      const document = await uploadDocument(file);
      setFiles((current) => [
        ...current,
        {
          id: document.id,
          name: document.original_filename,
          description:
            document.status === "READY"
              ? "Ready in your knowledge base"
              : "Indexing... searchable when ready",
        },
      ]);
    } catch {
      setError(
        "Could not process this document. Check the file contains readable text and try again.",
      );
    } finally {
      uploadBusy.current = false;
      setUploading(false);
    }
  }
  return (
    <div className="composer-wrap">
      {files.length > 0 && (
        <div className="file-chips" aria-live="polite">
          {files.map((file) => (
            <FileChip
              key={file.id}
              filename={file.name}
              description={file.description}
              onDismiss={() =>
                setFiles((current) =>
                  current.filter((item) => item.id !== file.id),
                )
              }
            />
          ))}
        </div>
      )}
      {uploading && (
        <p className="upload-status" role="status">
          Uploading and indexing your document…
        </p>
      )}
      {error && (
        <p className="chat-error" role="alert">
          {error}
        </p>
      )}
      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          if (!disabled && !uploading && draft.trim()) void onSend();
        }}
      >
        <input
          ref={input}
          type="file"
          accept=".pdf,.txt,.md"
          onChange={upload}
          hidden
        />
        <button
          className="upload-button"
          type="button"
          disabled={uploading || disabled}
          aria-label="Add a document to your knowledge base"
          title="Upload PDF, TXT, or Markdown (up to 10 MB)"
          onClick={() => input.current?.click()}
        >
          {uploading ? "…" : "+"}
        </button>
        <textarea
          ref={textarea}
          aria-label="Your question"
          value={draft}
          onChange={(event) => onDraft(event.target.value)}
          rows={1}
          maxLength={2000}
          disabled={disabled}
          placeholder="Ask about your documents…"
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <button
          className="send-button"
          type="submit"
          disabled={disabled || uploading || !draft.trim()}
          aria-label={sending ? "Generating answer" : "Send question"}
        >
          {sending ? "…" : "\u2191"}
        </button>
      </form>
      <p className="composer-note">
        Files join your knowledge base for all chats and become searchable after
        indexing. Verify important details against the sources.
      </p>
    </div>
  );
}
