"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Strategy } from "@/lib/api";

export default function BacktestPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);

  useEffect(() => {
    api.strategies().then(setStrategies);
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl">Backtest</h1>
      <p className="text-sm text-neutral-500">
        Run backtests from the CLI (<code className="font-mono">loom backtest --start … --end …</code>) or open a
        strategy to backtest a draft parameter change and compare it against the current version.
      </p>
      <div className="space-y-2">
        {strategies.map((s) => (
          <Link
            key={s.id}
            href={`/strategies/${s.id}`}
            className="block rounded-xl border border-black/10 dark:border-white/10 p-4 hover:bg-black/5 dark:hover:bg-white/5"
          >
            {s.name} →
          </Link>
        ))}
      </div>
    </div>
  );
}
