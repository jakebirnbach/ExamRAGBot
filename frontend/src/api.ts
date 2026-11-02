export interface Citation {
  source: string;
  page: number;
  page_end: number | null;
  label: string;
}

export interface Answer {
  text: string;
  citations: Citation[];
  grounded: boolean;
}

export interface QuizQuestion {
  question: string;
  reference_answer: string;
  citations: Citation[];
  topic: string | null;
}

export interface Grade {
  correct: boolean;
  feedback: string;
  score: number;
}

/** The server rejected the password. */
export class UnauthorizedError extends Error {}

export class ApiError extends Error {}

export interface Api {
  topics(): Promise<string[]>;
  ask(question: string, topics: string[]): Promise<Answer>;
  quiz(topics: string[]): Promise<QuizQuestion>;
  grade(question: string, referenceAnswer: string, answer: string): Promise<Grade>;
}

export function createApi(password: string): Api {
  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`/api${path}`, {
        method,
        headers: {
          Authorization: `Bearer ${password}`,
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError("Couldn't reach the server. Check your connection and try again.");
    }
    if (response.status === 401) throw new UnauthorizedError("Wrong password.");
    if (!response.ok) throw new ApiError(await errorMessage(response));
    return (await response.json()) as T;
  }

  return {
    topics: async () => (await request<{ topics: string[] }>("GET", "/topics")).topics,
    ask: (question, topics) => request("POST", "/ask", { question, topics }),
    quiz: (topics) => request("POST", "/quiz", { topics }),
    grade: (question, referenceAnswer, answer) =>
      request("POST", "/quiz/grade", {
        question,
        reference_answer: referenceAnswer,
        answer,
      }),
  };
}

async function errorMessage(response: Response): Promise<string> {
  const fallback = "Something went wrong. Please try again.";
  try {
    const { detail } = (await response.json()) as { detail?: unknown };
    return typeof detail === "string" ? detail : fallback;
  } catch {
    return fallback;
  }
}
