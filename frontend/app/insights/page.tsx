"use client";

import { useEffect, useState } from "react";
import { api, ChartBar, Digest, DigestEntry, SignalChart } from "@/lib/api";

function SignalChartView({ chart }: { chart: SignalChart }) {
  const bars = chart.bars;
  if (bars.length < 2) {
    return <p className="text-xs text-neutral-500">Not enough price history for a chart.</p>;
  }

  const w = 400;
  const h = 120;
  const closes = bars.map((b: ChartBar) => b.close);
  const min = Math.min(...closes, chart.trigger.price);
  const max = Math.max(...closes, chart.trigger.price);
  const range = max - min || 1;
  const x = (i: number) => (i / (bars.length - 1)) * w;
  const y = (v: number) => h - ((v - min) / range) * h;

  const points = bars.map((b: ChartBar, i: number) => `${x(i)},${y(b.close)}`).join(" ");
  let triggerIndex = bars.findIndex((b: ChartBar) => b.date >= chart.trigger.date);
  if (triggerIndex === -1) triggerIndex = bars.length - 1;

  return (
    <div className="space-y-2">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-28">
        <polyline points={points} fill="none" stroke="#6C7BFA" strokeWidth={2} />
        <line x1={x(triggerIndex)} y1={0} x2={x(triggerIndex)} y2={h} stroke="#FF8FCB" strokeWidth={1} strokeDasharray="3 3" />
        <circle cx={x(triggerIndex)} cy={y(chart.trigger.price)} r={4} fill="#FF8FCB" />
      </svg>
      <p className="text-xs text-neutral-500 font-numeric">
        Triggered {chart.trigger.action} @ £{chart.trigger.price.toFixed(2)} on {chart.trigger.date}
      </p>
      {chart.trigger.reasoning && (
        <p className="text-sm bg-black/5 dark:bg-white/5 rounded-xl p-3">{chart.trigger.reasoning}</p>
      )}
    </div>
  );
}

function DigestSection({ title, entries }: { title: string; entries: DigestEntry[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [charts, setCharts] = useState<Record<string, SignalChart>>({});

  async function toggle(entry: DigestEntry) {
    if (expanded === entry.signal_id) {
      setExpanded(null);
      return;
    }
    setExpanded(entry.signal_id);
    if (!charts[entry.signal_id]) {
      const chart = await api.signalChart(entry.signal_id);
      setCharts((prev) => ({ ...prev, [entry.signal_id]: chart }));
    }
  }

  return (
    <div className="space-y-2">
      <h2 className="text-lg">{title}</h2>
      {entries.length === 0 && <p className="text-sm text-neutral-500">Nothing here yet.</p>}
      <div className="space-y-2">
        {entries.map((entry) => (
          <div key={entry.signal_id} className="rounded-xl border border-black/10 dark:border-white/10 p-3 space-y-2">
            <button className="w-full text-left" onClick={() => toggle(entry)}>
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-medium text-sm">
                    {entry.action.toUpperCase()} {entry.instrument}
                    {entry.strategy_name ? ` · ${entry.strategy_name}` : ""}
                  </p>
                  <p className="text-sm text-neutral-500 mt-1">{entry.insight}</p>
                </div>
                <span className="text-xs rounded-full px-2 py-1 bg-amber/15 text-amber dark:text-amber-dark shrink-0">
                  {entry.status.replace("_", " ")}
                </span>
              </div>
            </button>
            {expanded === entry.signal_id &&
              (charts[entry.signal_id] ? (
                <SignalChartView chart={charts[entry.signal_id]} />
              ) : (
                <p className="text-xs text-neutral-500">Loading chart…</p>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function InsightsPage() {
  const [period, setPeriod] = useState<"daily" | "weekly">("daily");
  const [digest, setDigest] = useState<Digest | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .digest("demo", period)
      .then(setDigest)
      .catch((e) => setError((e as Error).message));
  }, [period]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl">Insights</h1>
        <div className="flex gap-1 rounded-full bg-black/5 dark:bg-white/10 p-1">
          {(["daily", "weekly"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 rounded-full text-sm capitalize ${
                period === p ? "bg-indigo/15 text-indigo dark:text-indigo-dark" : "hover:bg-black/5 dark:hover:bg-white/10"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="text-danger text-sm">{error}</p>}
      {digest && (
        <>
          <DigestSection title="Fired" entries={digest.fired} />
          <DigestSection title="Still watching" entries={digest.still_watching} />
        </>
      )}
    </div>
  );
}
