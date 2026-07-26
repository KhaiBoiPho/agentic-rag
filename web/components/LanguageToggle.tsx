"use client";

import { useT } from "@/lib/i18n";

export default function LanguageToggle() {
  const { lang, setLang, t } = useT();
  return (
    <button
      className="iconbtn lang-toggle"
      onClick={() => setLang(lang === "vi" ? "en" : "vi")}
      aria-label={t.nav.language}
      title={t.nav.language}
    >
      {lang === "vi" ? "VI" : "EN"}
    </button>
  );
}
