/**
 * Server-side proxy to the Loom API (ADR-0017).
 *
 * The browser calls this route on its own origin; this handler — which runs on the server, never
 * in the bundle — attaches the shared secret and forwards to the backend. That keeps LOOM_API_KEY
 * out of anything a user can read, and makes every API call same-origin, so no CORS and no
 * cross-site cookie concerns.
 *
 * `LOOM_API_BASE_URL` deliberately has no `NEXT_PUBLIC_` prefix: the API's address is now a
 * server-side concern too, since nothing in the browser talks to it directly.
 */

const API_BASE = process.env.LOOM_API_BASE_URL ?? "http://localhost:8000";
const API_KEY = process.env.LOOM_API_KEY ?? "";

// Hop-by-hop and body-framing headers belong to *this* connection, not the forwarded one —
// passing them through makes the upstream response undecodable (a re-compressed or re-chunked
// body advertised with the original framing).
const STRIPPED = new Set(["host", "connection", "content-length", "content-encoding", "transfer-encoding"]);

async function proxy(request: Request, path: string[]): Promise<Response> {
  const incoming = new URL(request.url);
  const target = `${API_BASE}/${path.join("/")}${incoming.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!STRIPPED.has(key.toLowerCase())) headers.set(key, value);
  });
  headers.set("X-Loom-Api-Key", API_KEY);

  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();

  const upstream = await fetch(target, { method: request.method, headers, body, cache: "no-store" });

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!STRIPPED.has(key.toLowerCase())) responseHeaders.set(key, value);
  });

  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

type Ctx = { params: { path: string[] } };

export const GET = (r: Request, { params }: Ctx) => proxy(r, params.path);
export const POST = (r: Request, { params }: Ctx) => proxy(r, params.path);
export const PATCH = (r: Request, { params }: Ctx) => proxy(r, params.path);
export const PUT = (r: Request, { params }: Ctx) => proxy(r, params.path);
export const DELETE = (r: Request, { params }: Ctx) => proxy(r, params.path);

// A proxy that Next.js statically optimised would serve a cached upstream response to a later,
// different request — wrong for an API whose responses are per-request account state.
export const dynamic = "force-dynamic";
