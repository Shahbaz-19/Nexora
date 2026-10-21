"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import {
  deleteDocument,
  getDocuments,
  uploadDocument,
  type DocumentItem,
  type DocumentStatus,
} from "@/lib/api";

const statusLabels: Record<DocumentStatus, string> = {
  UPLOADED: "Uploaded",
  PROCESSING: "Processing",
  READY: "Ready",
  FAILED: "Failed",
};

export default function KnowledgeBasePanel({
  onMenu,
}: {
  onMenu: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [pendingDelete, setPendingDelete] = useState<DocumentItem | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    mounted.current = true;

    return () => {
      mounted.current = false;
    };
  }, []);

  const loadDocuments = useCallback(async () => {
    try {
      const data = await getDocuments();
      if (mounted.current) setDocuments(data);
    } catch {
      if (mounted.current) setError("Could not load your knowledge base.");
    }
  }, []);

  useEffect(() => {
    getDocuments()
      .then((data) => {
        if (mounted.current) setDocuments(data);
      })
      .catch(() => {
        if (mounted.current) setError("Could not load your knowledge base.");
      })
      .finally(() => {
        if (mounted.current) setLoading(false);
      });
  }, []);

  useEffect(() => {
    const hasProcessingDocument = documents.some(
      (document) =>
        document.status === "PROCESSING" || document.status === "UPLOADED",
    );
    if (!hasProcessingDocument) return;

    let cancelled = false;
    const interval = window.setInterval(() => {
      if (!cancelled) void loadDocuments();
    }, 2500);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [documents, loadDocuments]);

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || uploading) return;

    setUploading(true);
    setError("");
    try {
      const document = await uploadDocument(file);
      setDocuments((current) => [document, ...current]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Document upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete || deletingId !== null) return;
    const document = pendingDelete;
    setDeletingId(document.id);
    setError("");
    try {
      await deleteDocument(document.id);
      setDocuments((current) =>
        current.filter((item) => item.id !== document.id),
      );
      setPendingDelete(null);
    } catch {
      setError("Could not delete this document. Please try again.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <section className="knowledge-main" aria-label="Knowledge base">
      <header className="chat-header">
        <button
          className="icon-button menu-toggle"
          aria-label="Open navigation"
          onClick={onMenu}
        >
          &#9776;
        </button>
        <h1>Knowledge Base</h1>
      </header>

      <div className="knowledge-scroll">
        <div className="knowledge-wrap">
          <div className="knowledge-hero">
            <div>
              <p className="eyebrow">DOCUMENT LIBRARY</p>
              <h2>Your searchable knowledge base</h2>
              <p>
                Manage the documents available to Nexora
                across all chats.
              </p>
            </div>
            <button
              className="knowledge-upload"
              disabled={uploading}
              onClick={() => input.current?.click()}
            >
              {uploading ? "Uploading..." : "Upload document"}
            </button>
            <input
              ref={input}
              type="file"
              accept=".pdf,.txt,.md"
              hidden
              onChange={handleUpload}
            />
          </div>

          {error && (
            <p className="knowledge-error" role="alert">
              {error}
            </p>
          )}

          <div className="knowledge-card">
            {loading ? (
              <div className="knowledge-state" role="status">
                Loading documents...
              </div>
            ) : documents.length === 0 ? (
              <div className="knowledge-empty">
                <div className="knowledge-empty-icon" aria-hidden="true">
                  +
                </div>
                <h3>No documents in your knowledge base yet.</h3>
                <p>Upload a PDF, TXT, or Markdown file to get started.</p>
                <button
                  className="knowledge-upload secondary"
                  disabled={uploading}
                  onClick={() => input.current?.click()}
                >
                  Upload document
                </button>
              </div>
            ) : (
              <div className="knowledge-list">
                {documents.map((document) => (
                  <DocumentRow
                    key={document.id}
                    document={document}
                    deleting={deletingId === document.id}
                    onDelete={() => setPendingDelete(document)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {pendingDelete && (
        <DeleteDialog
          document={pendingDelete}
          deleting={deletingId === pendingDelete.id}
          onCancel={() => {
            if (deletingId === null) setPendingDelete(null);
          }}
          onConfirm={confirmDelete}
        />
      )}
    </section>
  );
}

function DocumentRow({
  document,
  deleting,
  onDelete,
}: {
  document: DocumentItem;
  deleting: boolean;
  onDelete: () => void;
}) {
  return (
    <article className="knowledge-row">
      <div className="knowledge-file-type">{document.file_type}</div>
      <div className="knowledge-file-main">
        <h3 title={document.original_filename}>{document.original_filename}</h3>
        <div className="knowledge-meta">
          <span>{formatFileSize(document.file_size)}</span>
          <span>{document.chunk_count} chunks</span>
          <span>Uploaded {formatDate(document.created_at)}</span>
        </div>
        {document.status === "FAILED" && document.failure_reason && (
          <p className="knowledge-failure" title={document.failure_reason}>
            {document.failure_reason}
          </p>
        )}
      </div>
      <StatusBadge status={document.status} />
      <button
        className="knowledge-delete"
        disabled={deleting}
        onClick={onDelete}
      >
        {deleting ? "Deleting..." : "Delete"}
      </button>
    </article>
  );
}

function StatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <span className={`knowledge-status status-${status.toLowerCase()}`}>
      {statusLabels[status]}
    </span>
  );
}

function DeleteDialog({
  document,
  deleting,
  onCancel,
  onConfirm,
}: {
  document: DocumentItem;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation">
      <div
        className="delete-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-document-title"
      >
        <h2 id="delete-document-title">
          Delete &quot;{document.original_filename}&quot;?
        </h2>
        <p>
          This will permanently remove the document and its indexed knowledge
          from your searchable knowledge base.
        </p>
        <div className="delete-actions">
          <button className="dialog-cancel" disabled={deleting} onClick={onCancel}>
            Cancel
          </button>
          <button
            className="dialog-delete"
            disabled={deleting}
            onClick={onConfirm}
          >
            {deleting ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
