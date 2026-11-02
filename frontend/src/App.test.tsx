import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const TOPICS = ["M3 · Theory", "M4 · Interviewing"];
const CITATION = { source: "deck.pdf", page: 3, page_end: 5, label: "deck.pdf, pp. 3-5" };

type Handler = (body: Record<string, unknown>) => [number, unknown];

let handlers: Record<string, Handler>;
let calls: { path: string; auth: string | null; body: Record<string, unknown> }[];

function json(status: number, data: unknown): Response {
  return new Response(JSON.stringify(data), { status });
}

beforeEach(() => {
  calls = [];
  handlers = { "/api/topics": () => [200, { topics: TOPICS }] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init: RequestInit) => {
      const body = init.body ? (JSON.parse(init.body as string) as Record<string, unknown>) : {};
      const auth = new Headers(init.headers).get("Authorization");
      calls.push({ path, auth, body });
      if (auth !== "Bearer secret") return json(401, { detail: "Wrong password." });
      const [status, data] = handlers[path]!(body);
      return json(status, data);
    }),
  );
});

async function signIn(user: ReturnType<typeof userEvent.setup>) {
  render(<App />);
  await user.type(screen.getByLabelText("Password"), "secret{Enter}");
  await screen.findByRole("tab", { name: "Ask" });
}

describe("sign-in", () => {
  it("shows the error and stays out on a wrong password", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Password"), "nope{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong password.");
    expect(sessionStorage.length).toBe(0);
  });

  it("keeps the session across a reload and signs out", async () => {
    const user = userEvent.setup();
    const first = render(<App />);
    await user.type(screen.getByLabelText("Password"), "secret{Enter}");
    await screen.findByRole("tab", { name: "Ask" });
    first.unmount();

    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(sessionStorage.length).toBe(0);
  });

  it("returns to sign-in when the password stops working", async () => {
    const user = userEvent.setup();
    await signIn(user);
    handlers["/api/ask"] = () => [200, {}];
    vi.mocked(fetch).mockResolvedValueOnce(json(401, { detail: "Wrong password." }));
    await user.type(screen.getByLabelText("Your question"), "hi{Enter}");
    expect(await screen.findByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("sign in again");
  });
});

describe("ask", () => {
  it("sends the chosen topic and renders the answer with its sources", async () => {
    const user = userEvent.setup();
    await signIn(user);
    handlers["/api/ask"] = () => [
      200,
      { text: "**Six** stages [1].", citations: [CITATION], grounded: true },
    ];
    await user.selectOptions(screen.getByLabelText("Topic"), TOPICS[0]!);
    await user.type(screen.getByLabelText("Your question"), "Which stages?{Enter}");

    expect(await screen.findByText("Six")).toHaveProperty("tagName", "STRONG");
    expect(screen.getByText("deck.pdf, pp. 3-5")).toBeInTheDocument();
    expect(calls.at(-1)?.body).toEqual({ question: "Which stages?", topics: [TOPICS[0]] });
  });

  it("labels only answers that cite no course material", async () => {
    const user = userEvent.setup();
    await signIn(user);
    const label = "General answer, not from your course materials";

    handlers["/api/ask"] = () => [200, { text: "Cited [1].", citations: [CITATION], grounded: true }];
    await user.type(screen.getByLabelText("Your question"), "course{Enter}");
    await screen.findByText("Cited [1].");
    expect(screen.queryByText(label)).toBeNull();

    handlers["/api/ask"] = () => [200, { text: "Start early.", citations: [], grounded: false }];
    await user.type(screen.getByLabelText("Your question"), "plan{Enter}");
    await screen.findByText("Start early.");
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("does not render HTML from a model reply", async () => {
    const user = userEvent.setup();
    await signIn(user);
    handlers["/api/ask"] = () => [
      200,
      { text: "<img src=x onerror=alert(1)>", citations: [], grounded: false },
    ];
    await user.type(screen.getByLabelText("Your question"), "x{Enter}");
    await waitFor(() => expect(calls.at(-1)?.path).toBe("/api/ask"));
    await screen.findByRole("textbox", { name: "Your question" });
    expect(document.querySelector("img")).toBeNull();
  });

  it("offers a retry after a failure, using the original question", async () => {
    const user = userEvent.setup();
    await signIn(user);
    handlers["/api/ask"] = () => [502, { detail: "A service failed." }];
    await user.type(screen.getByLabelText("Your question"), "Retry me{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("A service failed.");

    handlers["/api/ask"] = () => [200, { text: "Fine now.", citations: [], grounded: true }];
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Fine now.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(calls.at(-1)?.body.question).toBe("Retry me");
  });
});

describe("quiz", () => {
  const QUESTION = {
    question: "Name the first stage.",
    reference_answer: "Precontemplation.",
    citations: [CITATION],
    topic: TOPICS[0],
  };

  it("hides the reference answer until graded, then tallies and moves on", async () => {
    const user = userEvent.setup();
    await signIn(user);
    handlers["/api/quiz"] = () => [200, QUESTION];
    handlers["/api/quiz/grade"] = () => [
      200,
      { correct: false, feedback: "Close, but incomplete.", score: 0.5 },
    ];
    await user.click(screen.getByRole("tab", { name: "Quiz me" }));
    await user.click(screen.getByRole("button", { name: "Start quiz" }));

    await screen.findByText(QUESTION.question);
    expect(screen.queryByText("Precontemplation.")).toBeNull();
    expect(screen.queryByText("deck.pdf, pp. 3-5")).toBeNull();

    await user.type(screen.getByLabelText("Your answer"), "Thinking");
    await user.click(screen.getByRole("button", { name: "Check my answer" }));

    expect(await screen.findByText("Partly right")).toBeInTheDocument();
    expect(screen.getByText("Precontemplation.")).toBeInTheDocument();
    expect(screen.getByText("deck.pdf, pp. 3-5")).toBeInTheDocument();
    expect(screen.getByText("1 answered · 50% average")).toBeInTheDocument();
    expect(calls.at(-1)?.body).toEqual({
      question: QUESTION.question,
      reference_answer: QUESTION.reference_answer,
      answer: "Thinking",
    });

    await user.click(screen.getByRole("button", { name: "Next question" }));
    expect(await screen.findByLabelText("Your answer")).toHaveValue("");
  });

  it("keeps the typed answer when grading fails", async () => {
    const user = userEvent.setup();
    await signIn(user);
    handlers["/api/quiz"] = () => [200, QUESTION];
    handlers["/api/quiz/grade"] = () => [502, { detail: "A service failed." }];
    await user.click(screen.getByRole("tab", { name: "Quiz me" }));
    await user.click(screen.getByRole("button", { name: "Start quiz" }));
    await user.type(await screen.findByLabelText("Your answer"), "My long answer");
    await user.click(screen.getByRole("button", { name: "Check my answer" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("A service failed.");
    expect(screen.getByLabelText("Your answer")).toHaveValue("My long answer");
  });
});
