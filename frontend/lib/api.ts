export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Environment = "demo" | "live";

export interface Strategy {
  id: string;
  key: string;
  name: string;
  style: string;
  live_enabled: boolean;
  approval_mode: "manual" | "auto_above_threshold" | "auto";
  approval_threshold: number;
  notify_threshold: number;
}

export interface ExitPlan {
  profit_target_pct: number | null;
  stop_loss_pct: number | null;
  time_exit_days: number | null;
}

export interface Signal {
  id: string;
  strategy_id: string;
  book_id: string;
  environment: Environment;
  instrument: string;
  signal_type: "entry" | "exit";
  action: string;
  confidence: number;
  exit_plan: ExitPlan;
  quantity: number;
  reference_price: number;
  status: string;
  requires_manual_approval: boolean;
  note: string | null;
  counterfactual_outcome: Record<string, unknown> | null;
  created_at: string;
  decided_at: string | null;
}

export interface Insight {
  id: string;
  signal_id: string;
  tier: string;
  content: string;
  created_at: string;
}

export interface Position {
  book_id: string;
  book_name: string;
  strategy_key: string | null;
  instrument: string;
  quantity: number;
  average_price: number;
}

export interface Overview {
  environment: Environment;
  cash: number;
  positions: Position[];
}

export interface ConfigVersion {
  id: string;
  version_number: number | null;
  status: "draft" | "promoted";
  params: Record<string, unknown>;
  note: string | null;
  created_at: string;
  promoted_at: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${init?.method ?? "GET"} ${path} -> ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  strategies: () => request<Strategy[]>("/strategies"),
  strategy: (id: string) => request<Strategy>(`/strategies/${id}`),
  updateStrategy: (id: string, body: Partial<Strategy>) =>
    request<Strategy>(`/strategies/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  configVersions: (strategyId: string) =>
    request<ConfigVersion[]>(`/strategies/${strategyId}/config-versions`),
  createDraft: (strategyId: string, params: Record<string, unknown>, note?: string) =>
    request<ConfigVersion>(`/strategies/${strategyId}/config-versions`, {
      method: "POST",
      body: JSON.stringify({ params, note }),
    }),
  promoteVersion: (strategyId: string, versionId: string) =>
    request<ConfigVersion>(`/strategies/${strategyId}/config-versions/${versionId}/promote`, {
      method: "POST",
    }),
  draftBacktest: (
    strategyId: string,
    body: { draft_params: Record<string, unknown>; universe: string[]; start: string; end: string; starting_capital?: number },
  ) =>
    request<{ backtest: unknown; current_version_id: string | null; param_diff: Record<string, unknown> }>(
      `/strategies/${strategyId}/draft-backtest`,
      { method: "POST", body: JSON.stringify({ strategy_id: strategyId, ...body }) },
    ),
  strategyTrades: (strategyId: string, environment: Environment = "demo") =>
    request<{ trades: unknown[]; equity_curve: { date: string | null; cumulative_return: number }[] }>(
      `/strategies/${strategyId}/trades?environment=${environment}`,
    ),

  signals: (environment: Environment = "demo", status?: string) =>
    request<Signal[]>(`/signals?environment=${environment}${status ? `&status=${status}` : ""}`),
  signalInsights: (signalId: string) => request<Insight[]>(`/signals/${signalId}/insights`),
  screenSignal: (signalId: string) => request<Insight>(`/signals/${signalId}/screen`, { method: "POST" }),
  approveSignal: (signalId: string, note?: string) =>
    request<Signal>(`/signals/${signalId}/approve`, { method: "POST", body: JSON.stringify({ note }) }),
  rejectSignal: (signalId: string, note?: string) =>
    request<Signal>(`/signals/${signalId}/reject`, { method: "POST", body: JSON.stringify({ note }) }),

  overview: (environment: Environment = "demo") => request<Overview>(`/overview?environment=${environment}`),
  history: (environment: Environment = "demo", filters?: { instrument?: string; sector?: string }) =>
    request<Signal[]>(
      `/history?environment=${environment}${filters?.instrument ? `&instrument=${encodeURIComponent(filters.instrument)}` : ""}${
        filters?.sector ? `&sector=${encodeURIComponent(filters.sector)}` : ""
      }`,
    ),

  killSwitch: (environment: Environment = "demo") =>
    request<{ environment: string; engaged: boolean }>(`/settings/kill-switch?environment=${environment}`),
  engageKillSwitch: (environment: Environment = "demo") =>
    request<{ environment: string; engaged: boolean }>(`/settings/kill-switch/engage?environment=${environment}`, {
      method: "POST",
    }),
  resumeKillSwitch: (environment: Environment = "demo") =>
    request<{ environment: string; engaged: boolean }>(`/settings/kill-switch/resume?environment=${environment}`, {
      method: "POST",
    }),

  runTradingPass: (environment: Environment = "demo") =>
    request<Signal[]>(`/trading-pass/run?environment=${environment}`, { method: "POST" }),

  books: (environment: Environment = "demo") =>
    request<{ id: string; name: string; strategy_id: string | null; strategy_key: string | null }[]>(
      `/books?environment=${environment}`,
    ),
  performance: (environment: Environment = "demo", filters?: { instrument?: string; sector?: string }) =>
    request<AggregatePerformance>(
      `/performance?environment=${environment}${filters?.instrument ? `&instrument=${encodeURIComponent(filters.instrument)}` : ""}${
        filters?.sector ? `&sector=${encodeURIComponent(filters.sector)}` : ""
      }`,
    ),
  correlation: (environment: Environment = "demo") =>
    request<{ books: { id: string; name: string }[]; matrix: (number | null)[][] }>(
      `/performance/correlation?environment=${environment}`,
    ),
};

export interface Metrics {
  num_trades: number;
  win_rate: number | null;
  profit_factor: number | null;
  expectancy_pct: number | null;
  max_drawdown_pct: number | null;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  rolling_sharpe: (number | null)[];
}

export interface CurvePoint {
  date: string;
  cumulative_return_pct: number;
  benchmark_return_pct: number | null;
}

export interface AggregatePerformance {
  environment: string;
  aggregate_metrics: Metrics;
  aggregate_curve: CurvePoint[];
  per_book: { book_id: string; book_name: string; strategy_key: string | null; metrics: Metrics }[];
}
