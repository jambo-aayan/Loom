"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const WEB_SHA = process.env.NEXT_PUBLIC_BUILD_SHA ?? "local";

function short(sha: string) {
  return /^[0-9a-f]{40}$/.test(sha) ? sha.slice(0, 7) : sha;
}

// Footer build identifier (T0.1): which commit the frontend and backend were built from, so a
// deploy that lags `main` is visible at a glance.
export function BuildInfo() {
  const [apiSha, setApiSha] = useState<string>("…");

  useEffect(() => {
    api
      .health()
      .then((h) => setApiSha(h.build_sha))
      .catch(() => setApiSha("unreachable"));
  }, []);

  return (
    <footer className="px-4 pt-2 pb-20 md:pb-3 text-center font-mono text-[11px] text-neutral-500">
      web {short(WEB_SHA)} · api {short(apiSha)}
    </footer>
  );
}
