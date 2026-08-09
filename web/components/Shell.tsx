"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useStore } from "@/lib/store";
import Sidebar from "./Sidebar";

interface ShellCtx {
  toggleSidebar: () => void;
  collapsed: boolean;
}
const Ctx = createContext<ShellCtx>({ toggleSidebar: () => {}, collapsed: false });
export const useShell = () => useContext(Ctx);

export default function Shell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const loadKbs = useStore((s) => s.loadKbs);
  const loadProjects = useStore((s) => s.loadProjects);
  const syncBackendConfig = useStore((s) => s.syncBackendConfig);

  // load shared data once; collapse by default on small screens
  useEffect(() => {
    if (window.innerWidth < 820) setCollapsed(true);
    loadKbs().catch(() => {});
    loadProjects().catch(() => {});
    // Best-effort: the bundled DEFAULT_MODEL constant already mirrors the
    // backend, so a failure here just leaves that in place.
    syncBackendConfig().catch(() => {});
  }, [loadKbs, loadProjects, syncBackendConfig]);

  return (
    <Ctx.Provider value={{ toggleSidebar: () => setCollapsed((c) => !c), collapsed }}>
      <div className={`shell${collapsed ? " collapsed" : ""}`}>
        <Sidebar onNavigate={() => window.innerWidth < 820 && setCollapsed(true)} />
        <div className="main">{children}</div>
      </div>
    </Ctx.Provider>
  );
}
