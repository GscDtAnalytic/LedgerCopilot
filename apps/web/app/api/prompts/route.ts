/**
 * Route handler: POST /api/prompts → FastAPI POST /api/v1/prompts.
 *
 * Same rationale as /api/review: the session JWT lives in a cookie this
 * server-side handler reads and forwards as a Bearer token. The FastAPI endpoint
 * enforces the admin-only check — this handler is a transport shim, not the
 * access boundary.
 */

import { NextResponse } from "next/server";
import { cookies } from "next/headers";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const cookieStore = await cookies();
  const token = cookieStore.get("lc_token")?.value;

  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const body = await request.json();

  const res = await fetch(`${API_BASE}/api/v1/prompts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errorBody = await res.text().catch(() => "");
    return NextResponse.json(
      { error: `Create failed: ${errorBody}` },
      { status: res.status },
    );
  }

  return NextResponse.json(await res.json(), { status: 201 });
}
