type MarketBar = { timestamp: string; close: string; volume: number };

async function bars(): Promise<MarketBar[]> {
  const api = process.env.EVENTALPHA_API_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${api}/api/v1/assets/ACME/bars?limit=12`, { cache: "no-store" });
    if (!response.ok) return [];
    return (await response.json()).data as MarketBar[];
  } catch { return []; }
}

export default async function LiveMarket() {
  const data = await bars();
  return <main><p style={{ color: "#77d9a7" }}>REPLAY MARKET DATA</p><h1>ACME live chart</h1><p>{data.length ? "1-minute replay bars. Data is not live market coverage." : "API unavailable; no market value is displayed."}</p><ul>{data.map((bar) => <li key={bar.timestamp}>{new Date(bar.timestamp).toLocaleTimeString()} - ${bar.close} - volume {bar.volume.toLocaleString()}</li>)}</ul><a href="/">Back</a></main>;
}
