"use client";

import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { Sun } from "./Icons";

function current(): "light" | "dark" {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "light" || attr === "dark") return attr;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function ThemeToggle() {
  const [mounted, setMounted] = useState(false);
  const { t } = useT();
  useEffect(() => setMounted(true), []);

  function toggle() {
    const next = current() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("cot.theme", next);
    } catch {
      /* ignore */
    }
  }

  return (
    <button className="iconbtn" onClick={toggle} aria-label={t.nav.theme} title={t.nav.theme}>
      {mounted ? <Sun /> : null}
    </button>
  );
}
