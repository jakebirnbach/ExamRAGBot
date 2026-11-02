import { type FormEvent, useState } from "react";

interface Props {
  error: string | null;
  onSubmit: (password: string) => Promise<void>;
}

export function Login({ error, onSubmit }: Props) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    await onSubmit(password);
    setBusy(false);
  }

  return (
    <form className="login" onSubmit={submit}>
      <h1>Study Assistant</h1>
      <label htmlFor="password">Password</label>
      <input
        id="password"
        type="password"
        autoComplete="current-password"
        autoFocus
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="primary" disabled={busy || !password}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
