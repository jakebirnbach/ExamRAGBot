import type { Citation } from "./api";

function pages(c: Citation): string {
  return c.page_end ? `pp. ${c.page}–${c.page_end}` : `p. ${c.page}`;
}

export function Sources({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="sources">
      <h3>Sources</h3>
      <ol>
        {citations.map((c, i) => (
          <li key={c.label}>
            <span className="source-number" aria-hidden="true">
              {i + 1}
            </span>
            <span className="source-name">{c.source.replace(/\.pdf$/i, "")}</span>
            <span className="source-pages">{pages(c)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
