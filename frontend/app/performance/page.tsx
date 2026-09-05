"use client";

import { useEffect, useState } from "react";
import { api, AggregatePerformance, CurvePoint, Metrics } from "@/lib/api";

function pct(v: number | null | undefined, digits = 1) {
  return v == null ? "—" : `${(v * 100).toFixed(digits)}%`;
}

function ratio(v: number | null | undefined) {
  return v == null ? "—" : v.toFixed(2);
}

function BenchmarkChart({ curve }: { curve: CurvePoint[] }) {
  if (curve.length < 2) return <p className="text-xs text-neutral-500">Not enough closed trades yet for a curve.</p>;
  const w = 400;
  const h = 100;
  const strategyVals = curve.map((p) => p.cumulative_return_pct);
  const benchVals = curve.map((p) => p.benchmark_return_pct ?? 0);
  const all = [...strategyVals, ...benchVals, 0];
  const min = Math.min(...all);
  const max = Math.max(...all);
  const range = max - min || 1;
  const toPoints = (vals: number[]) =>
    vals.map((v, i) => `${(i / (vals.length - 1)) * w},${h - ((v - min) / range) * h}`).join(" ");

  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-24">
        <polyline points={toPoints(strategyVals)} fill="none" stroke="#6C7BFA" strokeWidth={2} />
        <polyline points={toPoints(benchVals)} fill="none" stroke="#A86F0C" strokeWidth={2} strokeDasharray="4 3" />
      </svg>
      <div className="flex gap-4 text-xs mt-1 text-neutral-500">
        <span>
          <span className="inline-block w-3 h-0.5 bg-indigo align-middle mr-1" /> Strategy
        </span>
        <span>
          <span className="inline-block w-3 h-0.5 bg-amber align-middle mr-1" /> Benchmark (VWRL.L)
        </span>
      </div>
    </div>
  );
}

function MetricsGrid({ metrics }: { metrics: Metrics }) {
  const rows: [string, string][] = [
    ["Trades", String(metrics.num_trades)],
    ["Win rate", pct(metrics.win_rate)],
    ["Profit factor", ratio(metrics.profit_factor)],
    ["Expectancy / trade", pct(metrics.expectancy_pct)],
    ["Max drawdown", pct(metrics.max_drawdown_pct)],
    ["Sharpe", ratio(metrics.sharpe_ratio)],
    ["Sortino", ratio(metrics.sortino_ratio)],
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-numeric text-sm">
      {rows.map(([label, value]) => (
        <div key={label}>
          <p className="text-neutral-500 text-xs">{label}</p>
          <p>{value}</p>
        </div>
      ))}
    </div>
  );
}

function correlationColor(v: number | null): string {
  if (v == null) return "bg-black/5 dark:bg-white/5";
  if (v > 0.5) return "bg-pink/30";
  if (v < -0.5) return "bg-mint/30";
  return "bg-black/5 dark:bg-white/5";
}

function CorrelationMatrix({ books, matrix }: { books: { id: string; name: string }[]; matrix: (number | null)[][] }) {
  if (books.length < 2) {
    return <p className="text-xs text-neutral-500">Need at least two Books with trade history to compare.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="text-xs font-numeric border-collapse">
        <thead>
          <tr>
            <th className="p-1" />
            {books.map((b) => (
              <th key={b.id} className="p-1 text-left font-medium whitespace-nowrap">
                {b.name.split(" · ")[0]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {books.map((row, i) => (
            <tr key={row.id}>
              <td className="p-1 font-medium whitespace-nowrap">{row.name.split(" · ")[0]}</td>
              {books.map((_col, j) => (
                <td key={j} className={`p-1 text-center w-14 rounded ${correlationColor(matrix[i]?.[j] ?? null)}`}>
                  {matrix[i]?.[j] != null ? matrix[i][j]!.toFixed(2) : "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function PerformancePage() {
  const [data, setData] = useState<AggregatePerformance | null>(null);
  const [correlation, setCorrelation] = useState<{ books: { id: string; name: string }[]; matrix: (number | null)[][] } | null>(
    null,
  );
  const [instrument, setInstrument] = useState("");
  const [sector, setSector] = useState("");
  const [error, setError] = useState<string | null>(null);

  function load() {
    api
      .performance("demo", { instrument: instrument || undefined, sector: sector || undefined })
      .then(setData)
      .catch((e) => setError((e as Error).message));
  }

  useEffect(() => {
    load();
    api.correlation("demo").then(setCorrelation).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!data) return <p className="text-sm text-neutral-500">{error ?? "Loading…"}</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl">Performance</h1>
      {error && <p className="text-danger text-sm">{error}</p>}

      <div className="flex flex-wrap gap-2 items-center">
        <input
          placeholder="Filter by instrument (e.g. VUSA.L)"
          value={instrument}
          onChange={(e) => setInstrument(e.target.value)}
          className="rounded-lg border border-black/10 dark:border-white/10 bg-transparent px-3 py-1.5 text-sm"
        />
        <input
          placeholder="Filter by sector/industry"
          value={sector}
          onChange={(e) => setSector(e.target.value)}
          className="rounded-lg border border-black/10 dark:border-white/10 bg-transparent px-3 py-1.5 text-sm"
        />
        <button onClick={load} className="px-3 py-1.5 rounded-full bg-indigo text-white text-sm">
          Apply
        </button>
      </div>

      <div className="rounded-2xl border border-black/10 dark:border-white/10 p-5 space-y-3">
        <h2 className="text-lg">Aggregate (every Book)</h2>
        <BenchmarkChart curve={data.aggregate_curve} />
        <MetricsGrid metrics={data.aggregate_metrics} />
      </div>

      <div className="rounded-2xl border border-black/10 dark:border-white/10 p-5 space-y-3">
        <h2 className="text-lg">Cross-strategy correlation</h2>
        <p className="text-xs text-neutral-500">
          Weekly realized P&amp;L correlation across Books — are these strategies actually diversifying, or all
          moving together?
        </p>
        {correlation ? <CorrelationMatrix books={correlation.books} matrix={correlation.matrix} /> : null}
      </div>

      <div className="space-y-3">
        <h2 className="text-lg">Per Book</h2>
        {data.per_book.length === 0 && <p className="text-sm text-neutral-500">No books yet.</p>}
        {data.per_book.map((b) => (
          <div key={b.book_id} className="rounded-xl border border-black/10 dark:border-white/10 p-4 space-y-2">
            <p className="font-medium">{b.book_name}</p>
            <MetricsGrid metrics={b.metrics} />
          </div>
        ))}
      </div>
    </div>
  );
}
