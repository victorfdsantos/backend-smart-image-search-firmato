/**
 * Next.js App Router — Route Handler para POST /api/catalog/register
 *
 * Motivo: o proxy padrão do Next.js (rewrites) tem timeout de ~60s.
 * Operações longas (processamento de imagens + treino de embeddings) excedem
 * esse limite e resultam em 502/504 com body não-JSON, quebrando o frontend.
 *
 * Esta route handler usa fetch sem timeout e repassa o response completo,
 * contornando o limite do proxy.
 */

import { NextResponse } from "next/server";

// Desabilita o body size limit e o timeout do Edge runtime
export const runtime = "nodejs";
export const maxDuration = 1800; // 15 minutos (máximo no Vercel Pro / self-hosted ilimitado)

const AI_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function POST(): Promise<NextResponse> {
  try {
    const upstream = await fetch(`${AI_BASE}/catalog/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Node fetch não tem timeout nativo — a request aguarda até o backend responder
    });

    const data = await upstream.json();

    return NextResponse.json(data, { status: upstream.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { detail: `Proxy error: ${msg}` },
      { status: 502 }
    );
  }
}