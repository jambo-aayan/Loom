"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Overview } from "@/lib/api";

export default function OverviewPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function load() {
    try {
      setOverview(await api.overview("demo"));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function runPass() {
    setRunning(true);
    try {
      await api.runTradingPass("demo");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl">Overview</h1>
        <div className="flex items-center gap-2">
          <Link href="/performance" className="px-3 py-1.5 rounded-full bg-black/10 dark:bg-white/10 text-sm">
            Performance
          </Link>
          <button
            onClick={runPass}
            disabled={running}
            className="px-3 py-1.5 rounded-full bg-indigo text-white text-sm disabled:opacity-50"
          >
            {running ? "Running…" : "Run trading pass"}
          </button>
        </div>
      </div>

      {error && <p className="text-danger text-sm">{error}</p>}

      {overview && (
        <>
          <div className="rounded-2xl border border-black/10 dark:border-white/10 p-5">
            <p className="text-sm text-neutral-500">Cash (demo)</p>
            <p className="font-numeric text-3xl">£{overview.cash.toFixed(2)}</p>
          </div>

          <div>
            <h2 className="text-lg mb-2">Positions</h2>
            {overview.positions.length === 0 ? (
              <p className="text-sm text-neutral-500">No open positions yet.</p>
            ) : (
              <div className="space-y-2">
                {overview.positions.map((p) => (
                  <div
                    key={`${p.book_id}-${p.instrument}`}
                    className="flex items-center justify-between rounded-xl border border-black/10 dark:border-white/10 p-3"
                  >
                    <div>
                      <p className="font-medium">{p.instrument}</p>
                      <p className="text-xs text-neutral-500">{p.book_name}</p>
                    </div>
                    <div className="text-right font-numeric text-sm">
                      <p>{p.quantity.toFixed(4)} units</p>
                      <p className="text-neutral-500">avg £{p.average_price.toFixed(2)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
