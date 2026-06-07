import React, { useState, useRef, ReactNode } from "react";
import { Search, AlertTriangle, FileText, Loader2 } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { askQuestion, AskResponse } from "@/lib/askQuestion";
import { cn } from "@/lib/utils";

const SUGGESTED_QUESTIONS = [
  "Is Prof Odera a strict grader?",
  "Best neighborhoods in the Buenos Aires rotation?",
  "Which rotation city has the best healthcare?",
];

// --- Markdown renderer: bullet lines, **bold**, and [n] citations as superscripts ---
const renderAnswer = (
  text: string,
  onCitationClick: (n: number) => void
): ReactNode[] => {
  if (!text) return [];
  return text.split("\n").map((line, i) => {
    const parsed = line.replace(/^- /, "");
    const boldParts = parsed.split(/(\*\*.*?\*\*)/);

    const elements = boldParts.map((part, j) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return (
          <strong key={j} className="font-semibold text-zinc-900">
            {part.slice(2, -2)}
          </strong>
        );
      }

      const citationParts = part.split(/(\[\d+\])/);
      return citationParts.map((subpart, k) => {
        const match = subpart.match(/\[(\d+)\]/);
        if (match) {
          const num = parseInt(match[1], 10);
          return (
            <sup key={`${j}-${k}`} className="inline-flex">
              <button
                type="button"
                onClick={() => onCitationClick(num)}
                className="text-xs text-blue-700 hover:text-blue-900 hover:underline px-0.5 rounded cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400/50"
                data-testid={`citation-${num}`}
                title={`View source ${num}`}
              >
                [{num}]
              </button>
            </sup>
          );
        }
        return subpart;
      });
    });

    return (
      <li key={i} className="mb-3 pl-2 leading-relaxed">
        {elements}
      </li>
    );
  });
};

export default function Home() {
  const [question, setQuestion] = useState("");
  const [devState, setDevState] = useState<string>("high");
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState<AskResponse | null>(null);

  const sourceRefs = useRef<{ [key: number]: HTMLDivElement | null }>({});
  const [highlightedSource, setHighlightedSource] = useState<number | null>(null);

  const runAsk = async (q: string) => {
    if (!q.trim()) return;
    setQuestion(q);
    setIsLoading(true);
    setResponse(null);
    try {
      const res = await askQuestion(q, 5, devState);
      setResponse(res);
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    runAsk(question);
  };

  const handleCitationClick = (n: number) => {
    const el = sourceRefs.current[n];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setHighlightedSource(n);
      setTimeout(() => setHighlightedSource(null), 2000);
    }
  };

  return (
    <div className="min-h-[100dvh] bg-[#fcfcfc] text-zinc-800 font-serif selection:bg-blue-100 selection:text-blue-900 pb-24">
      {/* Dev-only preview-state switcher (hidden in production builds) */}
      {import.meta.env.DEV && (
      <div
        className="fixed top-4 right-4 z-50 bg-white border border-zinc-200 px-3 py-2 rounded shadow-sm text-xs font-sans flex items-center gap-2"
        data-testid="dev-controls"
      >
        <label className="font-medium text-zinc-500 uppercase tracking-wider text-[10px]">
          Preview state:
        </label>
        <Select value={devState} onValueChange={setDevState}>
          <SelectTrigger className="h-7 w-[150px] text-xs border-none shadow-none focus:ring-0 px-1 font-medium">
            <SelectValue placeholder="State" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="high">High Confidence</SelectItem>
            <SelectItem value="moderate">Moderate Confidence</SelectItem>
            <SelectItem value="low">Low Confidence</SelectItem>
            <SelectItem value="refused">Refused</SelectItem>
          </SelectContent>
        </Select>
      </div>
      )}

      {/* Header */}
      <header className="border-b border-zinc-200 bg-white py-12 px-6 lg:px-8">
        <div className="max-w-3xl mx-auto">
          <div className="mb-2 flex items-center gap-2 text-xs font-sans font-medium uppercase tracking-widest text-zinc-500">
            <span className="flex items-center gap-1.5 bg-zinc-100 px-2 py-1 rounded-sm">
              <AlertTriangle className="w-3.5 h-3.5" />
              Peer Opinions &middot; May be outdated
            </span>
          </div>
          <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight text-zinc-900 mb-4 font-serif">
            The Unofficial Guide to Minerva
          </h1>
          <p className="text-lg md:text-xl text-zinc-600 font-serif italic max-w-2xl leading-relaxed">
            Insider student knowledge from a private chat &mdash; opinions, not
            official policy.
          </p>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 lg:px-8 pt-12">
        {/* Query */}
        <section className="mb-16">
          <h2 className="text-sm font-sans font-semibold uppercase tracking-widest text-zinc-400 mb-4">
            Research Query
          </h2>
          <form onSubmit={handleSubmit} className="relative">
            <div className="relative group">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                <Search className="h-5 w-5 text-zinc-400" />
              </div>
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                disabled={isLoading}
                className="block w-full pl-12 pr-28 py-4 md:py-5 border-2 border-zinc-200 bg-white shadow-sm focus:outline-none focus:ring-0 focus:border-zinc-900 transition-colors text-lg md:text-xl placeholder:text-zinc-300 font-serif disabled:opacity-50"
                placeholder="Enter query..."
                data-testid="input-question"
              />
              <div className="absolute inset-y-0 right-0 flex items-center pr-2">
                <button
                  type="submit"
                  disabled={isLoading || !question.trim()}
                  className="bg-zinc-900 text-white px-4 py-2 text-sm font-sans font-medium uppercase tracking-wider hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center"
                  data-testid="button-ask"
                >
                  {isLoading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    "Search"
                  )}
                </button>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2 font-sans">
              {SUGGESTED_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => runAsk(q)}
                  disabled={isLoading}
                  className="text-xs bg-zinc-100 hover:bg-zinc-200 text-zinc-700 px-3 py-1.5 rounded transition-colors disabled:opacity-50"
                  data-testid={`button-suggested-${i}`}
                >
                  {q}
                </button>
              ))}
            </div>
          </form>
        </section>

        {/* Loading */}
        {isLoading && (
          <div className="flex flex-col items-center justify-center py-16 text-zinc-400 gap-3 font-sans">
            <Loader2 className="w-7 h-7 animate-spin" />
            <p className="text-sm font-medium">Searching student archives...</p>
          </div>
        )}

        {/* Findings */}
        {response && !isLoading && (
          <article className="bg-white border border-zinc-200 shadow-sm relative before:absolute before:left-0 before:top-0 before:bottom-0 before:w-1 before:bg-zinc-900">
            <div className="p-8 md:p-10">
              <header className="mb-8 border-b border-zinc-100 pb-6">
                <h2 className="text-sm font-sans font-semibold uppercase tracking-widest text-zinc-400 mb-2">
                  Findings
                </h2>

                {response.confidence === "moderate" && !response.refused && (
                  <div className="mt-4 flex gap-3 p-4 bg-amber-50/50 border border-amber-200 text-amber-900 rounded-sm font-sans text-sm">
                    <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
                    <div>
                      <strong className="font-semibold block mb-0.5">
                        Moderate confidence rating
                      </strong>
                      <span className="text-amber-800">
                        Available peer signals are limited. Double-check specifics.
                      </span>
                    </div>
                  </div>
                )}

                {response.confidence === "low" && !response.refused && (
                  <div className="mt-4 flex gap-3 p-4 bg-red-50/50 border border-red-200 text-red-900 rounded-sm font-sans text-sm">
                    <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
                    <div>
                      <strong className="font-semibold block mb-0.5">
                        Low confidence rating
                      </strong>
                      <span className="text-red-800">
                        Weak match in chat history. Treat as a weak signal.
                      </span>
                    </div>
                  </div>
                )}
              </header>

              <div className="prose prose-lg prose-zinc font-serif max-w-none text-zinc-800">
                {response.refused ? (
                  <p className="text-zinc-500 italic" data-testid="text-refused">
                    The chat doesn't have a clear answer on that.
                  </p>
                ) : (
                  <ul className="list-disc pl-5 space-y-2 marker:text-zinc-300">
                    {renderAnswer(response.answer, handleCitationClick)}
                  </ul>
                )}
              </div>
            </div>

            {!response.refused && response.sources.length > 0 && (
              <footer className="bg-zinc-50 border-t border-zinc-200 p-8 md:p-10">
                <h3 className="text-sm font-sans font-semibold uppercase tracking-widest text-zinc-400 mb-6 flex items-center gap-2">
                  <FileText className="w-4 h-4" /> Source Material
                </h3>

                <div className="space-y-8">
                  {response.sources.map((source) => (
                    <div
                      key={source.n}
                      ref={(el) => {
                        sourceRefs.current[source.n] = el;
                      }}
                      className={cn(
                        "group font-sans rounded -mx-4 px-4 py-2 transition-colors duration-500",
                        highlightedSource === source.n ? "bg-amber-100" : ""
                      )}
                      data-testid={`source-${source.n}`}
                    >
                      <div className="flex items-baseline gap-3 mb-2">
                        <span className="font-mono text-xs font-bold text-zinc-400 bg-zinc-200 px-1.5 py-0.5 rounded-sm">
                          [{source.n}]
                        </span>
                        <div className="text-xs text-zinc-500 flex flex-wrap items-center gap-2">
                          <strong className="text-zinc-700 font-semibold">
                            {source.topic}
                          </strong>
                          <span className="text-zinc-300">&bull;</span>
                          <span>{source.date}</span>
                          <span className="text-zinc-300">&bull;</span>
                          <span className="text-zinc-400">
                            Relevance: {source.relevance.toFixed(1)}
                          </span>
                        </div>
                      </div>

                      <blockquote className="pl-4 border-l-2 border-zinc-300 py-1 pr-4">
                        <p className="font-mono text-sm text-zinc-600 leading-relaxed">
                          "{source.excerpt}"
                        </p>
                      </blockquote>
                    </div>
                  ))}
                </div>
              </footer>
            )}
          </article>
        )}
      </main>
    </div>
  );
}
