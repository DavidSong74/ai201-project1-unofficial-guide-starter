import React, { useState, useRef, ReactNode } from "react";
import { Search, AlertTriangle, FileText, Loader2 } from "lucide-react";
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
          <strong key={j} className="font-semibold text-foreground">
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
      const res = await askQuestion(q, 5);
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
    <div className="min-h-[100dvh] bg-background text-foreground font-serif selection:bg-primary/20 selection:text-primary-foreground pb-24">
      {/* Header */}
      <header className="border-b border-border bg-card py-12 px-6 lg:px-8">
        <div className="max-w-3xl mx-auto">
          <div className="mb-2 flex items-center gap-2 text-xs font-sans font-medium uppercase tracking-widest text-muted-foreground">
            <span className="flex items-center gap-1.5 bg-muted px-2 py-1 rounded-sm text-foreground">
              <AlertTriangle className="w-3.5 h-3.5" />
              Pulling from 45,179+ texts &middot; Updated last on Jun 6, 2026
            </span>
          </div>
          <div className="flex items-center gap-4 mb-4">
            <img src="/minervalogo_copy.png" alt="Minerva logo" className="w-10 h-10 md:w-12 md:h-12 rounded-sm shadow-sm" />
            <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight text-foreground font-serif">
              The Unofficial Guide to Minerva
            </h1>
          </div>
          <p className="text-lg md:text-xl text-muted-foreground font-serif italic max-w-2xl leading-relaxed">
            Insider student wisdom from Minerva Cross-Class Chat &mdash; consult the accumulated wisdom of Minervan students.
          </p>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 lg:px-8 pt-12">
        {/* Query */}
        <section className="mb-16">
          <h2 className="text-sm font-sans font-semibold uppercase tracking-widest text-muted-foreground mb-4">
            Research Query
          </h2>
          <form onSubmit={handleSubmit} className="relative">
            <div className="relative group">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                <Search className="h-5 w-5 text-muted-foreground" />
              </div>
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                disabled={isLoading}
                className="block w-full pl-12 pr-28 py-4 md:py-5 border-2 border-border bg-background shadow-sm focus:outline-none focus:ring-0 focus:border-foreground transition-colors text-lg md:text-xl placeholder:text-muted-foreground/60 font-serif disabled:opacity-50"
                placeholder="Enter query..."
                data-testid="input-question"
              />
              <div className="absolute inset-y-0 right-0 flex items-center pr-2">
                <button
                  type="submit"
                  disabled={isLoading || !question.trim()}
                  className="bg-foreground text-background px-4 py-2 text-sm font-sans font-medium uppercase tracking-wider hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center"
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
                  className="text-xs bg-muted hover:bg-muted/80 text-muted-foreground hover:text-foreground px-3 py-1.5 rounded transition-colors disabled:opacity-50"
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
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3 font-sans">
            <Loader2 className="w-7 h-7 animate-spin" />
            <p className="text-sm font-medium">Searching student archives...</p>
          </div>
        )}

        {/* Findings */}
        {response && !isLoading && (
          <article className="bg-card border border-border shadow-sm relative before:absolute before:left-0 before:top-0 before:bottom-0 before:w-1 before:bg-foreground">
            <div className="p-8 md:p-10">
              <header className="mb-8 border-b border-border pb-6">
                <h2 className="text-sm font-sans font-semibold uppercase tracking-widest text-muted-foreground mb-2">
                  Findings
                </h2>

                {response.confidence === "moderate" && !response.refused && (
                  <div className="mt-4 flex gap-3 p-4 bg-amber-500/10 border border-amber-500/20 text-foreground rounded-sm font-sans text-sm">
                    <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
                    <div>
                      <strong className="font-semibold block mb-0.5">
                        Moderate confidence rating
                      </strong>
                      <span className="text-muted-foreground">
                        Available peer signals are limited. Double-check specifics.
                      </span>
                    </div>
                  </div>
                )}

                {response.confidence === "low" && !response.refused && (
                  <div className="mt-4 flex gap-3 p-4 bg-red-500/10 border border-red-500/20 text-foreground rounded-sm font-sans text-sm">
                    <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
                    <div>
                      <strong className="font-semibold block mb-0.5">
                        Low confidence rating
                      </strong>
                      <span className="text-muted-foreground">
                        Weak match in chat history. Treat as a weak signal.
                      </span>
                    </div>
                  </div>
                )}
              </header>

              <div className="prose prose-lg prose-zinc dark:prose-invert font-serif max-w-none text-foreground">
                {response.refused ? (
                  <p className="text-muted-foreground italic" data-testid="text-refused">
                    The chat doesn't have a clear answer on that.
                  </p>
                ) : (
                  <ul className="list-disc pl-5 space-y-2 marker:text-muted-foreground/40">
                    {renderAnswer(response.answer, handleCitationClick)}
                  </ul>
                )}
              </div>
            </div>

            {!response.refused && response.sources.length > 0 && (
              <footer className="bg-muted/40 border-t border-border p-8 md:p-10">
                <h3 className="text-sm font-sans font-semibold uppercase tracking-widest text-muted-foreground mb-6 flex items-center gap-2">
                  <img src="/minervalogo.png" alt="logo" className="w-6 h-6" /> Source Material
                </h3>

                <div className="space-y-8">
                  {response.sources.map((source) => (
                    <div
                      key={source.n}
                      ref={(el) => {
                        sourceRefs.current[source.n] = el;
                      }}
                      className={cn(
                        "group font-sans rounded px-4 py-2 transition-colors duration-500 w-full",
                        highlightedSource === source.n ? "bg-amber-500/10" : ""
                      )}
                      data-testid={`source-${source.n}`}
                    >
                      <div className="flex items-baseline gap-3 mb-2">
                        <span className="font-mono text-xs font-bold text-muted-foreground bg-muted px-1.5 py-0.5 rounded-sm">
                          [{source.n}]
                        </span>
                        <div className="text-xs text-muted-foreground flex flex-wrap items-center gap-2">
                          <strong className="text-foreground font-semibold">
                            {source.topic}
                          </strong>
                          <span className="text-muted-foreground/40">&bull;</span>
                          <span>{source.date}</span>
                          <span className="text-muted-foreground/40">&bull;</span>
                          <span className="text-muted-foreground">
                            Relevance: {source.relevance.toFixed(1)}
                          </span>
                        </div>
                      </div>

                      <blockquote className="pl-4 border-l-2 border-border py-1 pr-4">
                        <p className="font-mono text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap break-words max-w-full">
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
