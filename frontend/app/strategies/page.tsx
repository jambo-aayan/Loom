"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Strategy } from "@/lib/api";

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);

  useEffect(() => {
    api.strategies().then(setStrategies);
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl">Strategies</h1>
      <div className="space-y-2">
        {strategies.map((s) => (
          <Link
            key={s.id}
            href={`/strategies/${s.id}`}
            className="block rounded-xl border border-black/10 dark:border-white/10 p-4 hover:bg-black/5 dark:hover:bg-white/5"
          >
            <p className="font-medium">{s.name}</p>
            <p className="text-xs text-neutral-500">
              {s.style} · {s.live_enabled ? "live-enabled" : "demo only"}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
