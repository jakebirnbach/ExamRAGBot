import { useCallback, useEffect, useMemo, useState } from "react";
import { type Api, createApi, UnauthorizedError } from "./api";
import { AskView } from "./AskView";
import { Login } from "./Login";
import { QuizView } from "./QuizView";

const PASSWORD_KEY = "study-assistant-password";

function readPassword(): string | null {
  try {
    return sessionStorage.getItem(PASSWORD_KEY);
  } catch {
    return null;
  }
}

function writePassword(password: string | null): void {
  try {
    if (password === null) sessionStorage.removeItem(PASSWORD_KEY);
    else sessionStorage.setItem(PASSWORD_KEY, password);
  } catch {
    // Storage can be blocked; the password then lasts only until a reload.
  }
}

type Mode = "ask" | "quiz";

export function App() {
  const [password, setPassword] = useState(readPassword);
  const [topics, setTopics] = useState<string[] | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  const signOut = useCallback((message: string | null) => {
    writePassword(null);
    setPassword(null);
    setTopics(null);
    setLoginError(message);
  }, []);

  const signIn = useCallback(
    async (candidate: string) => {
      setLoginError(null);
      try {
        const loaded = await createApi(candidate).topics();
        writePassword(candidate);
        setPassword(candidate);
        setTopics(loaded);
      } catch (error) {
        setLoginError((error as Error).message);
      }
    },
    [],
  );

  // A password kept from earlier in this tab: reload the topics, or ask again if it's stale.
  useEffect(() => {
    if (password === null || topics !== null) return;
    let cancelled = false;
    createApi(password)
      .topics()
      .then((loaded) => {
        if (!cancelled) setTopics(loaded);
      })
      .catch((error: Error) => {
        if (!cancelled) signOut(error instanceof UnauthorizedError ? null : error.message);
      });
    return () => {
      cancelled = true;
    };
  }, [password, topics, signOut]);

  const api = useMemo(() => (password === null ? null : createApi(password)), [password]);

  if (api === null) return <Login error={loginError} onSubmit={signIn} />;
  if (topics === null) return <p className="splash">Loading…</p>;
  return (
    <Workspace
      api={api}
      topics={topics}
      onExpired={() => signOut("Please sign in again.")}
      onSignOut={() => signOut(null)}
    />
  );
}

interface WorkspaceProps {
  api: Api;
  topics: string[];
  onExpired: () => void;
  onSignOut: () => void;
}

function Workspace({ api, topics, onExpired, onSignOut }: WorkspaceProps) {
  const [mode, setMode] = useState<Mode>("ask");
  const [topic, setTopic] = useState("");
  const selected = useMemo(() => (topic ? [topic] : []), [topic]);

  return (
    <div className="app">
      <header className="masthead">
        <h1>Study Assistant</h1>
        <button type="button" className="link" onClick={onSignOut}>
          Sign out
        </button>
      </header>

      <div className="controls">
        <div className="tabs" role="tablist" aria-label="Mode">
          {(["ask", "quiz"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              className={mode === m ? "tab active" : "tab"}
              onClick={() => setMode(m)}
            >
              {m === "ask" ? "Ask" : "Quiz me"}
            </button>
          ))}
        </div>
        <label className="topic">
          <span>Topic</span>
          <select value={topic} onChange={(e) => setTopic(e.target.value)}>
            <option value="">All topics</option>
            {topics.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Both stay mounted so switching tabs keeps the conversation and the current question. */}
      <main hidden={mode !== "ask"}>
        <AskView api={api} topics={selected} onExpired={onExpired} />
      </main>
      <main hidden={mode !== "quiz"}>
        <QuizView api={api} topics={selected} onExpired={onExpired} />
      </main>
    </div>
  );
}
