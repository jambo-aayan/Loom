"use client";

import { useEffect, useState } from "react";
import { api, Strategy } from "@/lib/api";

export default function SettingsPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [killEngaged, setKillEngaged] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [s, k] = await Promise.all([api.strategies(), api.killSwitch("demo")]);
      setStrategies(s);
      setKillEngaged(k.engaged);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function toggleKillSwitch() {
    if (killEngaged) {
      await api.resumeKillSwitch("demo");
    } else {
      await api.engageKillSwitch("demo");
    }
    await load();
  }

  async function toggleLiveEnabled(strategy: Strategy) {
    await api.updateStrategy(strategy.id, { live_enabled: !strategy.live_enabled });
    await load();
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl">Settings</h1>
      {error && <p className="text-danger text-sm">{error}</p>}

      <div className="rounded-2xl border border-black/10 dark:border-white/10 p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-medium">Kill switch (demo)</p>
            <p className="text-xs text-neutral-500">
              Blocks every order submission the instant it&rsquo;s engaged (checked before each submission, not just
              once per pass).
            </p>
          </div>
          <button
            onClick={toggleKillSwitch}
            className={`px-4 py-1.5 rounded-full text-sm font-medium ${
              killEngaged ? "bg-danger text-white" : "bg-black/10 dark:bg-white/10"
            }`}
          >
            {killEngaged ? "Engaged — resume" : "Engage"}
          </button>
        </div>
      </div>

      <div className="space-y-3">
        <h2 className="text-lg">Strategies</h2>
        {strategies.map((s) => (
          <div key={s.id} className="rounded-xl border border-black/10 dark:border-white/10 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <p className="font-medium">{s.name}</p>
              <button
                onClick={() => toggleLiveEnabled(s)}
                className={`text-xs px-3 py-1 rounded-full ${
                  s.live_enabled ? "bg-mint/30" : "bg-black/10 dark:bg-white/10"
                }`}
              >
                Live: {s.live_enabled ? "enabled" : "disabled"}
              </button>
            </div>
            <p className="text-xs text-neutral-500">
              Approval mode: {s.approval_mode} · threshold {s.approval_threshold} · notify {s.notify_threshold}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
