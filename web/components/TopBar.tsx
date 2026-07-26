"use client";

import ThemeToggle from "./ThemeToggle";
import LanguageToggle from "./LanguageToggle";

export default function TopBar({ title, right }: { title: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="topbar">
      <h1>{title}</h1>
      <span className="spacer" />
      {right}
      <LanguageToggle />
      <ThemeToggle />
    </div>
  );
}
