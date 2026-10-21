import type { ChatSource } from "@/lib/api";
export default function SourceCard({ source }: { source: ChatSource }) {
  return (
    <div className="source-card">
      <span className="file-type">
        {source.filename.split(".").pop()?.toUpperCase() || "FILE"}
      </span>
      <p title={source.filename}>{source.filename}</p>
      <small>
        {source.page_number !== null && <>Page {source.page_number} • </>}Chunk{" "}
        {source.chunk_index + 1}
      </small>
    </div>
  );
}
