type Event = { event_id: string; canonical_title: string; event_type: string; first_received_at: string; mentions: unknown[]; source_independence: number };

async function events(): Promise<Event[]> {
  const api = process.env.EVENTALPHA_API_URL ?? "http://127.0.0.1:8000";
  try { const response = await fetch(`${api}/api/v1/events`, { cache: "no-store" }); return response.ok ? ((await response.json()).data as Event[]) : []; } catch { return []; }
}

export default async function EventRadar() {
  const data = await events();
  return <main><p style={{ color: "#77d9a7" }}>REPLAY EVENT RADAR</p><h1>Global events</h1>{data.length ? <ul>{data.map((event) => <li key={event.event_id}><strong>{event.canonical_title}</strong><br />{event.event_type}; {event.mentions.length} source mention(s); source independence {event.source_independence}; received {new Date(event.first_received_at).toLocaleString()}</li>)}</ul> : <p>Event feed unavailable. No event count is presented as zero data.</p>}<a href="/">Back</a></main>;
}
