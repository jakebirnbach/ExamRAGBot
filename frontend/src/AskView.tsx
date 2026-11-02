import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { type Answer, type Api, UnauthorizedError } from "./api";
import { Sources } from "./Sources";

interface Exchange {
  id: number;
  question: string;
  topics: string[];
  answer?: Answer;
  error?: string;
}

interface Props {
  api: Api;
  topics: string[];
  onExpired: () => void;
}

export function AskView({ api, topics, onExpired }: Props) {
  const [draft, setDraft] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);
  const lastExchange = useRef<HTMLElement>(null);
  const latest = exchanges[exchanges.length - 1];

  useEffect(() => {
    // Top of the latest exchange, so a long answer is read from its start.
    lastExchange.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [exchanges]);

  async function run(id: number, question: string, scope: string[]) {
    setBusy(true);
    const update = (patch: Partial<Exchange>) =>
      setExchanges((all) => all.map((x) => (x.id === id ? { ...x, ...patch } : x)));
    try {
      update({ answer: await api.ask(question, scope), error: undefined });
    } catch (error) {
      if (error instanceof UnauthorizedError) return onExpired();
      update({ error: (error as Error).message });
    } finally {
      setBusy(false);
    }
  }

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const question = draft.trim();
    if (!question || busy) return;
    const id = nextId.current++;
    setExchanges((all) => [...all, { id, question, topics }]);
    setDraft("");
    void run(id, question, topics);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) submit(event);
  }

  return (
    <>
      {exchanges.length === 0 && (
        <p className="intro">
          Ask anything. When your course materials cover it, the answer comes from them, with the
          file and page to check. Anything else is labelled as a general answer.
        </p>
      )}

      <div className="conversation">
        {exchanges.map((x) => (
          <article
            key={x.id}
            className="exchange"
            ref={x.id === latest?.id ? lastExchange : undefined}
          >
            <p className="question">{x.question}</p>
            {x.answer && (
              <div className="answer">
                {!x.answer.grounded && (
                  <p className="general-note">General answer, not from your course materials</p>
                )}
                <Markdown>{x.answer.text}</Markdown>
                <Sources citations={x.answer.citations} />
              </div>
            )}
            {x.error && (
              <div className="error" role="alert">
                <p>{x.error}</p>
                <button
                  type="button"
                  className="link"
                  disabled={busy}
                  onClick={() => void run(x.id, x.question, x.topics)}
                >
                  Try again
                </button>
              </div>
            )}
            {!x.answer && !x.error && (
              <p className="pending" role="status">
                Reading your course materials…
              </p>
            )}
          </article>
        ))}
      </div>

      <form className="composer" onSubmit={submit}>
        <label htmlFor="question" className="visually-hidden">
          Your question
        </label>
        <textarea
          id="question"
          rows={2}
          maxLength={2000}
          placeholder="Ask a question…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button type="submit" className="primary" disabled={busy || !draft.trim()}>
          Ask
        </button>
        {latest && (
          <p className="hint">Each question is answered on its own, so include the full context.</p>
        )}
      </form>
    </>
  );
}
