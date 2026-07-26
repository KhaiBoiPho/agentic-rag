"use client";

import ThemeToggle from "./ThemeToggle";
import LanguageToggle from "./LanguageToggle";
import { useShell } from "./Shell";
import { useT } from "@/lib/i18n";
import { Menu } from "./Icons";

export default function TopBar({ title, right }: { title: React.ReactNode; right?: React.ReactNode }) {
  const { toggleSidebar } = useShell();
  const { t } = useT();
  return (
    <div className="topbar">
      <button className="iconbtn" onClick={toggleSidebar} aria-label={t.nav.toggleSidebar}>
        <Menu />
      </button>
      <h1>{title}</h1>
      <span className="spacer" />
      {right}
      <LanguageToggle />
      <ThemeToggle />
    </div>
  );
}
