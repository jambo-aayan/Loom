"use client";

import { useEffect, useState } from "react";
import { api, Strategy } from "@/lib/api";

export default function SettingsPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [killEngaged, setKillEngaged] = useState(false);
  const [liveTradingEnabled, setLiveTradingEnabled] = useState(false);
  const [autoTradingEnabled, setAutoTradingEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [s, k, live, auto] = await Promise.all([
        api.strategies(),
        api.killSwitch("demo"),
        api.liveTradingGate(),
        api.autoTradingGate(),
      ]);
      setStrategies(s);
      setKillEngaged(k.engaged);
      setLiveTradingEnabled(live.enabled);
      setAutoTradingEnabled(auto.enabled);
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

  async function toggleLiveTradingGate() {
    if (liveTradingEnabled) {
      await api.disableLiveTradingGate();
    } else {
      await api.enableLiveTradingGate();
    }
    await load();
  }

  async function toggleAutoTradingGate() {
    if (autoTradingEnabled) {
      await api.disableAutoTradingGate();
    } else {
      await api.enableAutoTradingGate();
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
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <p className="font-medium">Live trading</p>
            <p className="text-xs text-neutral-500">
              Off by default. While off, Loom refuses to place a single live order — regardless of any strategy&rsquo;s
              own Live setting — and Live isn&rsquo;t selectable anywhere in the app.
            </p>
          </div>
          <button
            onClick={toggleLiveTradingGate}
            className={`shrink-0 self-start sm:self-auto px-4 py-1.5 rounded-full text-sm font-medium ${
              liveTradingEnabled ? "bg-mint/30" : "bg-black/10 dark:bg-white/10"
            }`}
          >
            {liveTradingEnabled ? "Enabled — disable" : "Disabled — enable"}
          </button>
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 dark:border-white/10 p-5 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <p className="font-medium">Auto trades</p>
            <p className="text-xs text-neutral-500">
              Off by default. While off, every signal — regardless of a strategy&rsquo;s own approval mode or
              confidence — waits in Approvals for you. Turning this on restores each strategy&rsquo;s own configured
              behavior immediately.
            </p>
          </div>
          <button
            onClick={toggleAutoTradingGate}
            className={`shrink-0 self-start sm:self-auto px-4 py-1.5 rounded-full text-sm font-medium ${
              autoTradingEnabled ? "bg-mint/30" : "bg-black/10 dark:bg-white/10"
            }`}
          >
            {autoTradingEnabled ? "Enabled — disable" : "Disabled — enable"}
          </button>
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 dark:border-white/10 p-5 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <p className="font-medium">Kill switch (demo)</p>
            <p className="text-xs text-neutral-500">
              Blocks every order submission the instant it&rsquo;s engaged (checked before each submission, not just
              once per pass).
            </p>
          </div>
          <button
            onClick={toggleKillSwitch}
            className={`shrink-0 self-start sm:self-auto px-4 py-1.5 rounded-full text-sm font-medium ${
              killEngaged ? "bg-danger text-white" : "bg-black/10 dark:bg-white/10"
            }`}
          >
            {killEngaged ? "Engaged — resume" : "Engage"}
          </button>
        </div>
      </div>

      <div className="space-y-3">
        <h2 className="text-lg">Strategies</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
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
    </div>
  );
}
