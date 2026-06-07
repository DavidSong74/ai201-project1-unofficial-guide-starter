// TODO: backend wires here — swap this function for a real POST /ask call
export type Confidence = "high" | "moderate" | "low";

export interface Source {
  n: number;
  source_file: string;
  topic: string;
  date: string;
  relevance: number;
  excerpt: string;
}

export interface AskResponse {
  answer: string;
  refused: boolean;
  confidence: Confidence;
  sources: Source[];
}

const MOCK_HIGH: AskResponse = {
  answer: "- One student calls Prof Odera a **very hard grader** with strict standards [1][2].\n- Another: \"super strict\" but a genuinely lovely person [3].\n- Grades can improve with effort and office hours, though he's reportedly gotten stricter over time [2].\n- Consensus: strict, **not** an easy grader [1][2][3].",
  refused: false,
  confidence: "high",
  sources: [
    { n: 1, source_file: "prof-reviews.txt", topic: "Prof reviews", date: "2023-01-04", relevance: 8.7, excerpt: "Is prof. Odera strict with grades? … He is quite strict with grades, not so much with CP, but he isn't the easy-grader you're looking for." },
    { n: 2, source_file: "prof-reviews.txt", topic: "Prof reviews", date: "2026-05-19", relevance: 5.3, excerpt: "Incredibly wonderful human. Very hard grader. I've never felt more considered in a class than with Odera, but both classes were some of my lowest grades." },
    { n: 3, source_file: "prof-reviews.txt", topic: "Prof reviews", date: "2025-09-06", relevance: 3.7, excerpt: "Very lovely as a person, goes straight to the point, cold-calls a lot; assignment instructions are heavy." }
  ]
};

const MOCK_MODERATE: AskResponse = {
  answer: "- Buenos Aires is generally well-liked for its affordable rent and vibrant nightlife [1].\n- Palermo and Villa Crespo are frequently recommended neighborhoods [2].\n- Commute to the co-working space is short from most central barrios [1][2].",
  refused: false,
  confidence: "moderate",
  sources: [
    { n: 1, source_file: "ba-rotation.txt", topic: "Buenos Aires neighborhoods", date: "2024-08-12", relevance: 6.1, excerpt: "Palermo Soho is pricier but very convenient. Villa Crespo is the sweet spot — cheaper, walkable, great coffee." },
    { n: 2, source_file: "ba-rotation.txt", topic: "Buenos Aires rotation", date: "2023-11-20", relevance: 4.3, excerpt: "Honestly any barrio near Line D metro is fine. Avoid Microcentro for day-to-day living." }
  ]
};

const MOCK_LOW: AskResponse = {
  answer: "- Berlin and Seoul both have strong public healthcare systems by student accounts [1].\n- Some mention Seoul's hospital experience as particularly efficient [1].",
  refused: false,
  confidence: "low",
  sources: [
    { n: 1, source_file: "rotation-tips.txt", topic: "Healthcare by city", date: "2022-09-01", relevance: 2.1, excerpt: "I got sick in Seoul and the hospital was shockingly fast and cheap. Berlin was fine too but lots of waiting." }
  ]
};

const MOCK_REFUSED: AskResponse = {
  answer: "",
  refused: true,
  confidence: "low",
  sources: []
};

const MOCKS: Record<string, AskResponse> = {
  high: MOCK_HIGH,
  moderate: MOCK_MODERATE,
  low: MOCK_LOW,
  refused: MOCK_REFUSED
};

export async function askQuestion(
  question: string,
  k: number = 5,
  _devState?: string
): Promise<AskResponse> {
  // Wired to the FastAPI backend (api.py), proxied by Vite from "/ask" -> :8000.
  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, k }),
    });
    if (!res.ok) throw new Error(`/ask responded ${res.status}`);
    return (await res.json()) as AskResponse;
  } catch (err) {
    // Backend not running (e.g. design preview): fall back to mock data so the UI
    // still renders. The dev-only state switcher selects which mock to show.
    console.warn("askQuestion: backend unavailable, using mock data —", err);
    await new Promise((r) => setTimeout(r, 400));
    return (_devState && MOCKS[_devState]) || MOCK_HIGH;
  }
}
