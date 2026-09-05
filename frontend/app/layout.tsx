import type { Metadata, Viewport } from "next";
import { NavShell } from "@/components/NavShell";
import { RegisterServiceWorker } from "@/components/RegisterServiceWorker";
import "./globals.css";

export const metadata: Metadata = {
  title: "Loom",
  description: "Systematic Trading 212 trading bot dashboard.",
  manifest: "/manifest.json",
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "Loom" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F3F2EF" },
    { media: "(prefers-color-scheme: dark)", color: "#0B0C0F" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- shared across every page via the root layout, not a single page */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Tiro+Bangla&family=Space+Grotesk:wght@500;600&family=IBM+Plex+Sans:wght@400;500&family=IBM+Plex+Mono:wght@400;500&display=swap"
        />
      </head>
      <body>
        <RegisterServiceWorker />
        <NavShell>{children}</NavShell>
      </body>
    </html>
  );
}
