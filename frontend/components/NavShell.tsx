"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const PRIMARY_NAV = [
  { href: "/", label: "Overview", icon: "◧" },
  { href: "/approvals", label: "Approvals", icon: "✓" },
  { href: "/strategies", label: "Strategies", icon: "◆" },
  { href: "/backtest", label: "Backtest", icon: "▤" },
  { href: "/insights", label: "Insights", icon: "✺" },
] as const;

const HEADER_ICONS = [
  { href: "/history", label: "History", icon: "↺" },
  { href: "/settings", label: "Settings", icon: "⚙" },
] as const;

export function NavShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? window.localStorage.getItem("loom-theme") : null;
    const isDark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    setDark(isDark);
    document.documentElement.classList.toggle("dark", isDark);
  }, []);

  function toggleTheme() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    window.localStorage.setItem("loom-theme", next ? "dark" : "light");
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-4 py-3 border-b border-black/10 dark:border-white/10">
        <Link href="/" className="font-wordmark text-xl text-indigo dark:text-indigo-dark">
          loom
        </Link>
        <nav className="hidden md:flex items-center gap-1">
          {PRIMARY_NAV.map((item) => (
            <NavLink key={item.href} href={item.href} label={item.label} active={pathname === item.href} />
          ))}
        </nav>
        <div className="flex items-center gap-1">
          {HEADER_ICONS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-label={item.label}
              className={`w-9 h-9 grid place-items-center rounded-full text-lg ${
                pathname === item.href
                  ? "bg-indigo/15 text-indigo dark:text-indigo-dark"
                  : "hover:bg-black/5 dark:hover:bg-white/10"
              }`}
            >
              {item.icon}
            </Link>
          ))}
          <button
            onClick={toggleTheme}
            aria-label="Toggle theme"
            className="w-9 h-9 grid place-items-center rounded-full hover:bg-black/5 dark:hover:bg-white/10"
          >
            {dark ? "☀" : "☾"}
          </button>
        </div>
      </header>

      <main className="flex-1 px-4 py-4 pb-20 md:pb-4 max-w-5xl w-full mx-auto">{children}</main>

      <nav className="md:hidden fixed bottom-0 inset-x-0 grid grid-cols-5 border-t border-black/10 dark:border-white/10 bg-ground-light/95 dark:bg-ground-dark/95 backdrop-blur">
        {PRIMARY_NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex flex-col items-center gap-0.5 py-2 text-xs ${
              pathname === item.href ? "text-indigo dark:text-indigo-dark" : "text-neutral-500"
            }`}
          >
            <span className="text-lg">{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

function NavLink({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      className={`px-3 py-1.5 rounded-full text-sm ${
        active ? "bg-indigo/15 text-indigo dark:text-indigo-dark" : "hover:bg-black/5 dark:hover:bg-white/10"
      }`}
    >
      {label}
    </Link>
  );
}
