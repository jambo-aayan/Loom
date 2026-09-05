"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ConfigVersion, Strategy } from "@/lib/api";

interface TradeLog {
  trades: { instrument: string; action: string; quantity: number; fill_price: number | null; filled_at: string | null }[];
  equity_curve: { date: string | null; cumulative_return: number }[];
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return <p className="text-xs text-neutral-500">Not enough trades yet for a curve.</p>;
  const w = 320;
  const h = 80;
  const min = Math.min(...points, 0);
  const max = Math.max(...points, 0);
  const range = max - min || 1;
  const coords = points
    .map((p, i) => `${(i / (points.length - 1)) * w},${h - ((p - min) / range) * h}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-20">
      <polyline points={coords} fill="none" stroke="#6C7BFA" strokeWidth={2} />
    </svg>
  );
}

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [versions, setVersions] = useState<ConfigVersion[]>([]);
  const [tradeLog, setTradeLog] = useState<TradeLog | null>(null);
  const [draftParams, setDraftParams] = useState("");
  const [draftResult, setDraftResult] = useState<{ backtest: unknown; param_diff: Record<string, unknown> } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [s, v, t] = await Promise.all([api.strategy(id), api.configVersions(id), api.strategyTrades(id, "demo")]);
      setStrategy(s);
      setVersions(v);
      setTradeLog(t as TradeLog);
      const current = v.find((x) => x.status === "promoted");
      setDraftParams(JSON.stringify(current?.params ?? {}, null, 2));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function runDraftBacktest() {
    try {
      const parsed = JSON.parse(draftParams);
      const result = await api.draftBacktest(id, {
        draft_params: parsed,
        universe: ["VUSA.L", "VWRL.L"],
        start: "2023-01-02",
        end: "2023-06-30",
      });
      setDraftResult(result);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function saveAsDraftAndPromote() {
    const parsed = JSON.parse(draftParams);
    const created = await api.createDraft(id, parsed, "Edited via Strategy detail page");
    await api.promoteVersion(id, created.id);
    await load();
    setDraftResult(null);
  }

  if (!strategy) return <p className="text-sm text-neutral-500">{error ?? "Loading…"}</p>;

  const curve = tradeLog?.equity_curve.map((p) => p.cumulative_return) ?? [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl">{strategy.name}</h1>
      {error && <p className="text-danger text-sm">{error}</p>}

      <div className="rounded-2xl border border-black/10 dark:border-white/10 p-5">
        <h2 className="text-lg mb-2">Live cumulative return</h2>
        <Sparkline points={curve} />
      </div>

      <div className="rounded-2xl border border-black/10 dark:border-white/10 p-5">
        <h2 className="text-lg mb-2">Trade log</h2>
        {(tradeLog?.trades.length ?? 0) === 0 ? (
          <p className="text-sm text-neutral-500">No filled trades yet.</p>
        ) : (
          <div className="space-y-1 text-sm font-numeric">
            {tradeLog!.trades.map((t, i) => (
              <div key={i} className="flex justify-between">
                <span>
                  {t.action} {t.instrument}
                </span>
                <span>
                  {t.quantity.toFixed(4)} @ {t.fill_price?.toFixed(2) ?? "—"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-black/10 dark:border-white/10 p-5">
        <h2 className="text-lg mb-2">Config version changelog</h2>
        <div className="space-y-2">
          {versions.map((v) => (
            <div key={v.id} className="text-sm flex justify-between border-b border-black/5 dark:border-white/5 pb-1">
              <span>
                {v.status === "promoted" ? `v${v.version_number}` : "draft"} {v.note ? `— ${v.note}` : ""}
              </span>
              <span className="text-neutral-500">{v.status}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 dark:border-white/10 p-5 space-y-3">
        <h2 className="text-lg">Backtest a draft parameter change</h2>
        <textarea
          value={draftParams}
          onChange={(e) => setDraftParams(e.target.value)}
          rows={8}
          className="w-full font-mono text-xs rounded-lg border border-black/10 dark:border-white/10 bg-transparent p-2"
        />
        <div className="flex gap-2">
          <button onClick={runDraftBacktest} className="px-3 py-1.5 rounded-full bg-indigo text-white text-sm">
            Backtest draft
          </button>
          {draftResult && (
            <button onClick={saveAsDraftAndPromote} className="px-3 py-1.5 rounded-full bg-mint text-black text-sm">
              Promote this version
            </button>
          )}
        </div>
        {draftResult && (
          <div className="text-xs font-numeric space-y-2">
            <div>
              <p className="font-medium mb-1">Parameter diff vs current</p>
              <pre className="bg-black/5 dark:bg-white/5 rounded-lg p-2 overflow-x-auto">
                {JSON.stringify(draftResult.param_diff, null, 2)}
              </pre>
            </div>
            <div>
              <p className="font-medium mb-1">Backtest stats</p>
              <pre className="bg-black/5 dark:bg-white/5 rounded-lg p-2 overflow-x-auto">
                {JSON.stringify((draftResult.backtest as { stats: unknown }).stats, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
