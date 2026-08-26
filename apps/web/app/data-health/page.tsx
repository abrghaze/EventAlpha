type Provider = { name: string; status: string; freshness_ms: number | null; detail?: string };

async function providers(): Promise<Provider[]> {
  const api = process.env.EVENTALPHA_API_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${api}/api/v1/providers/health`, { cache: "no-store" });
    return response.ok ? ((await response.json()).providers as Provider[]) : [];
  } catch { return []; }
}

export default async function DataHealth() {
  const data = await providers();
  return <main><p style={{ color: "#77d9a7" }}>PROVIDER HEALTH</p><h1>Data health</h1>{data.length ? <ul>{data.map((provider) => <li key={provider.name}><strong>{provider.name}</strong>: {provider.status}, freshness {provider.freshness_ms ?? "unavailable"} ms. {provider.detail}</li>)}</ul> : <p>Provider health is unavailable; this is not represented as healthy data.</p>}<a href="/">Back</a></main>;
}
