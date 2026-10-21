export default function FileChip({
  filename,
  description = "Added to your knowledge base",
  onDismiss,
}: {
  filename: string;
  description?: string;
  onDismiss: () => void;
}) {
  return (
    <div className="file-chip">
      <span className="file-type">
        {filename.split(".").pop()?.toUpperCase()}
      </span>
      <div>
        <strong title={filename}>{filename}</strong>
        <small>{description}</small>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label={`Dismiss ${filename} notification`}
        title="Dismiss notification; keep document"
      >
        ×
      </button>
    </div>
  );
}
