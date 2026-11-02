import { type FormEvent, useState } from "react";
import { type Api, type Grade, type QuizQuestion, UnauthorizedError } from "./api";
import { Sources } from "./Sources";

interface Props {
  api: Api;
  topics: string[];
  onExpired: () => void;
}

type Busy = "question" | "grade" | null;

function verdict(grade: Grade): string {
  if (grade.correct) return "Correct";
  return grade.score > 0 ? "Partly right" : "Not quite";
}

export function QuizView({ api, topics, onExpired }: Props) {
  const [question, setQuestion] = useState<QuizQuestion | null>(null);
  const [answer, setAnswer] = useState("");
  const [grade, setGrade] = useState<Grade | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [tally, setTally] = useState({ answered: 0, points: 0 });

  async function attempt(kind: Exclude<Busy, null>, action: () => Promise<void>) {
    setBusy(kind);
    setError(null);
    try {
      await action();
    } catch (e) {
      if (e instanceof UnauthorizedError) return onExpired();
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const nextQuestion = () =>
    attempt("question", async () => {
      const next = await api.quiz(topics);
      setQuestion(next);
      setAnswer("");
      setGrade(null);
    });

  function submitAnswer(event: FormEvent) {
    event.preventDefault();
    if (!question || !answer.trim()) return;
    void attempt("grade", async () => {
      const result = await api.grade(question.question, question.reference_answer, answer.trim());
      setGrade(result);
      setTally((t) => ({ answered: t.answered + 1, points: t.points + result.score }));
    });
  }

  const nextLabel = busy === "question" ? "Writing a question…" : "Next question";

  return (
    <>
      {tally.answered > 0 && (
        <p className="tally">
          {tally.answered} answered · {Math.round((tally.points / tally.answered) * 100)}% average
        </p>
      )}

      {!question && (
        <div className="quiz-start">
          <p className="intro">
            Get a short-answer question from your materials, write your answer in your own words,
            and see how it compares to what the course says.
          </p>
          <button
            type="button"
            className="primary"
            disabled={busy !== null}
            onClick={() => void nextQuestion()}
          >
            {busy === "question" ? "Writing a question…" : "Start quiz"}
          </button>
        </div>
      )}

      {question && (
        <section className="card">
          {question.topic && <p className="eyebrow">{question.topic}</p>}
          <h2 className="quiz-question">{question.question}</h2>

          {!grade && (
            <form onSubmit={submitAnswer}>
              <label htmlFor="answer" className="visually-hidden">
                Your answer
              </label>
              <textarea
                id="answer"
                rows={5}
                maxLength={8000}
                placeholder="Your answer…"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
              />
              <div className="actions">
                <button
                  type="submit"
                  className="primary"
                  disabled={busy !== null || !answer.trim()}
                >
                  {busy === "grade" ? "Checking…" : "Check my answer"}
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy !== null}
                  onClick={() => void nextQuestion()}
                >
                  {busy === "question" ? "Writing a question…" : "Skip"}
                </button>
              </div>
            </form>
          )}

          {grade && (
            <>
              <div className={grade.correct ? "verdict good" : "verdict"} role="status">
                <div className="verdict-row">
                  <strong>{verdict(grade)}</strong>
                  <span>{Math.round(grade.score * 100)}%</span>
                </div>
                <div className="meter" aria-hidden="true">
                  <div style={{ width: `${Math.round(grade.score * 100)}%` }} />
                </div>
              </div>
              <p>{grade.feedback}</p>
              <h3>Your answer</h3>
              <p className="prewrap">{answer.trim()}</p>
              <h3>What the course says</h3>
              <p>{question.reference_answer}</p>
              <Sources citations={question.citations} />
              <div className="actions">
                <button
                  type="button"
                  className="primary"
                  disabled={busy !== null}
                  onClick={() => void nextQuestion()}
                >
                  {nextLabel}
                </button>
              </div>
            </>
          )}
        </section>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}
