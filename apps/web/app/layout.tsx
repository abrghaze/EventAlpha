import type { Metadata } from "next";

export const metadata: Metadata = { title: "EventAlpha", description: "Evidence-driven market intelligence" };

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body style={{ fontFamily: "system-ui", margin: "3rem", background: "#09111f", color: "#e6edf7" }}>{children}</body></html>;
}
