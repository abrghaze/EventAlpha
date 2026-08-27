type StorageMode = "persistent" | "ephemeral";

type MarketBar = {
  provider: string;
  timestamp: string;
  bar_end_at: string;
  provider_updated_at: string | null;
  received_at: string;
  close: string;
  volume: number | null;
};

type MarketQuote = {
  provider: string;
  provider_timestamp: string | null;
  received_at: string;
  bid: string | null;
  ask: string | null;
  last: string | null;
};

type BarsPayload = {
  data: MarketBar[];
  source: string;
  storage: StorageMode;
  availability: "available" | "unavailable";
  latest_received_at: string | null;
  bar_freshness_ms?: number | null;
  stale?: boolean;
};

type SnapshotPayload = {
  quote: MarketQuote;
  quote_freshness_ms: number | null;
  stale: boolean;
  source: string;
  storage: StorageMode;
};

type ChartSample = {
  bar: MarketBar;
  price: number;
  timestampMs: number;
};

type ChartGeometry = {
  segments: string[];
  isolatedPoints: { x: number; y: number }[];
  gapCount: number;
  firstTimestampMs: number;
  lastTimestampMs: number;
};

const QUOTE_STALE_AFTER_MS = 15_000;
const BAR_STALE_AFTER_MS = 90_000;
const EXPECTED_BAR_INTERVAL_MS = 60_000;

async function readApi<T>(path: string): Promise<T | null> {
  const api = process.env.EVENTALPHA_API_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${api}${path}`, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

function parseTimestamp(value: string | null): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function ageMs(value: string | null, nowMs: number): number | null {
  const timestampMs = parseTimestamp(value);
  if (timestampMs === null || timestampMs > nowMs) return null;
  return nowMs - timestampMs;
}

function formatAge(value: number | null): string {
  if (value === null) return "age unavailable";
  if (value < 1_000) return `${value} ms old`;
  if (value < 60_000) return `${Math.floor(value / 1_000)} s old`;
  if (value < 3_600_000) return `${Math.floor(value / 60_000)} min old`;
  return `${Math.floor(value / 3_600_000)} h old`;
}

function formatTimestamp(value: string | null): string {
  const timestampMs = parseTimestamp(value);
  return timestampMs === null ? "unavailable" : new Date(timestampMs).toLocaleString();
}

function chartSamples(data: MarketBar[]): ChartSample[] {
  return data
    .map((bar) => {
      const timestampMs = parseTimestamp(bar.timestamp);
      const price = bar.close.trim() === "" ? Number.NaN : Number(bar.close);
      return { bar, price, timestampMs };
    })
    .filter(
      (sample): sample is ChartSample =>
        sample.timestampMs !== null && Number.isFinite(sample.price) && sample.price > 0,
    )
    .sort((left, right) => left.timestampMs - right.timestampMs);
}

function chartGeometry(samples: ChartSample[]): ChartGeometry | null {
  if (!samples.length) return null;

  const width = 720;
  const height = 240;
  const padding = 24;
  const minimum = Math.min(...samples.map((sample) => sample.price));
  const maximum = Math.max(...samples.map((sample) => sample.price));
  const priceRange = maximum - minimum || 1;
  const firstTimestampMs = samples[0].timestampMs;
  const lastTimestampMs = samples.at(-1)?.timestampMs ?? firstTimestampMs;
  const timeRange = lastTimestampMs - firstTimestampMs;

  const points = samples.map((sample) => ({
    x:
      timeRange === 0
        ? width / 2
        : padding +
          ((sample.timestampMs - firstTimestampMs) / timeRange) * (width - padding * 2),
    y:
      height -
      padding -
      ((sample.price - minimum) / priceRange) * (height - padding * 2),
    timestampMs: sample.timestampMs,
  }));

  const grouped: typeof points[] = [];
  for (const point of points) {
    const current = grouped.at(-1);
    const previous = current?.at(-1);
    if (
      !current ||
      (previous && point.timestampMs - previous.timestampMs > EXPECTED_BAR_INTERVAL_MS * 1.5)
    ) {
      grouped.push([point]);
    } else {
      current.push(point);
    }
  }

  return {
    segments: grouped
      .filter((segment) => segment.length > 1)
      .map((segment) =>
        segment.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" "),
      ),
    isolatedPoints: grouped
      .filter((segment) => segment.length === 1)
      .map((segment) => ({ x: segment[0].x, y: segment[0].y })),
    gapCount: Math.max(grouped.length - 1, 0),
    firstTimestampMs,
    lastTimestampMs,
  };
}

function sourceDescription(
  barsPayload: BarsPayload | null,
  snapshotPayload: SnapshotPayload | null,
): { label: string; replay: boolean; unavailable: boolean } {
  const provider =
    barsPayload?.source ||
    snapshotPayload?.source ||
    barsPayload?.data[0]?.provider ||
    snapshotPayload?.quote.provider ||
    null;
  const persisted =
    barsPayload?.storage === "persistent" || snapshotPayload?.storage === "persistent";
  const replay = provider?.toLowerCase().includes("replay") === true;

  if (!provider) return { label: "MARKET DATA UNAVAILABLE", replay: false, unavailable: true };
  if (replay) {
    return {
      label: persisted ? "PERSISTED REPLAY MARKET DATA" : "REPLAY MARKET DATA",
      replay: true,
      unavailable: false,
    };
  }
  return {
    label: `${persisted ? "PERSISTED " : ""}${provider.toUpperCase()} MARKET DATA`,
    replay: false,
    unavailable: false,
  };
}

export default async function LiveMarket() {
  const [barsPayload, snapshotPayload] = await Promise.all([
    readApi<BarsPayload>("/api/v1/assets/ACME/bars?limit=30"),
    readApi<SnapshotPayload>("/api/v1/assets/ACME/snapshot"),
  ]);
  const samples = chartSamples(barsPayload?.data ?? []);
  const geometry = chartGeometry(samples);
  const latestSample = samples.at(-1) ?? null;
  const prices = samples.map((sample) => sample.price);
  const minimum = prices.length ? Math.min(...prices) : null;
  const maximum = prices.length ? Math.max(...prices) : null;
  const nowMs = Date.now();

  const quoteTimestamp =
    snapshotPayload?.quote.provider_timestamp ?? snapshotPayload?.quote.received_at ?? null;
  const measuredQuoteAgeMs = ageMs(quoteTimestamp, nowMs);
  const quoteAgeMs = snapshotPayload?.quote_freshness_ms ?? measuredQuoteAgeMs;
  const quoteStale =
    snapshotPayload === null ||
    snapshotPayload.stale ||
    measuredQuoteAgeMs === null ||
    measuredQuoteAgeMs > QUOTE_STALE_AFTER_MS;

  const barReferenceTimestamp =
    latestSample?.bar.provider_updated_at ?? latestSample?.bar.bar_end_at ?? null;
  const measuredBarAgeMs = ageMs(barReferenceTimestamp, nowMs);
  const barAgeMs = barsPayload?.bar_freshness_ms ?? measuredBarAgeMs;
  const barsUnavailable =
    barsPayload === null || barsPayload.availability === "unavailable" || geometry === null;
  const barsStale =
    barsUnavailable ||
    barsPayload?.stale === true ||
    measuredBarAgeMs === null ||
    measuredBarAgeMs > BAR_STALE_AFTER_MS;

  const source = sourceDescription(barsPayload, snapshotPayload);
  const statusColor =
    source.unavailable || barsUnavailable
      ? "#f08b8b"
      : source.replay || quoteStale || barsStale
        ? "#e5b45f"
        : "#77d9a7";

  return (
    <main>
      <p style={{ color: statusColor }}>
        {source.label} - LIVE TRADING DISABLED
      </p>
      <h1>ACME 1-minute market chart</h1>

      <section aria-label="Market freshness">
        <h2>Freshness</h2>
        {snapshotPayload ? (
          <p style={{ color: quoteStale ? "#e5b45f" : "#77d9a7" }}>
            Quote: {snapshotPayload.quote.last ? `$${snapshotPayload.quote.last}` : "last price unavailable"}
            {" - "}
            {formatAge(quoteAgeMs)} - {quoteStale ? "STALE" : "fresh"}
          </p>
        ) : (
          <p style={{ color: "#f08b8b" }}>
            Quote unavailable; no zero-price substitute is displayed.
          </p>
        )}
        {barsUnavailable ? (
          <p style={{ color: "#f08b8b" }}>
            Finalized bars unavailable; no zero-value chart is displayed.
          </p>
        ) : (
          <p style={{ color: barsStale ? "#e5b45f" : "#77d9a7" }}>
            Latest finalized bar: {formatAge(barAgeMs)} - {barsStale ? "STALE" : "fresh"}
          </p>
        )}
      </section>

      {!barsUnavailable && geometry && latestSample ? (
        <>
          <p>
            Latest ${latestSample.bar.close} - range ${minimum?.toFixed(2)}-${maximum?.toFixed(2)} -
            dataset last received {formatTimestamp(barsPayload?.latest_received_at ?? null)}
          </p>
          <svg
            aria-label="ACME close-price history; missing time intervals appear as gaps"
            role="img"
            viewBox="0 0 720 260"
            style={{ width: "100%", maxWidth: 900, background: "#101a2b", borderRadius: 12 }}
          >
            <line x1="24" y1="216" x2="696" y2="216" stroke="#36506f" />
            <line x1="24" y1="24" x2="24" y2="216" stroke="#36506f" />
            {geometry.segments.map((points, index) => (
              <polyline
                key={`${points}-${index}`}
                points={points}
                fill="none"
                stroke={barsStale ? "#e5b45f" : "#77d9a7"}
                strokeWidth="4"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ))}
            {geometry.isolatedPoints.map((point, index) => (
              <circle
                key={`${point.x}-${point.y}-${index}`}
                cx={point.x}
                cy={point.y}
                r="4"
                fill={barsStale ? "#e5b45f" : "#77d9a7"}
              />
            ))}
            <text x="24" y="244" fill="#a9b8cc" fontSize="12">
              {new Date(geometry.firstTimestampMs).toISOString().slice(11, 16)} UTC
            </text>
            <text x="650" y="244" fill="#a9b8cc" fontSize="12">
              {new Date(geometry.lastTimestampMs).toISOString().slice(11, 16)} UTC
            </text>
          </svg>
          <p>
            {samples.length} finalized observations. Missing volume remains explicit: {latestSample.bar.volume?.toLocaleString() ?? "unavailable"}.
            {geometry.gapCount > 0
              ? ` ${geometry.gapCount} missing time interval${geometry.gapCount === 1 ? " is" : "s are"} shown as a chart break.`
              : " No missing 1-minute intervals are present in this window."}
          </p>
        </>
      ) : null}
      <a href="/">Back</a>
    </main>
  );
}
