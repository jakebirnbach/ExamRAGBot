import type { Citation } from "./api";

export function Sources({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="sources">
      <h3>Sources</h3>
      <ol>
        {citations.map((c) => (
          <li key={c.label}>{c.label}</li>
        ))}
      </ol>
    </div>
  );
}
