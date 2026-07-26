"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useStore } from "@/lib/store";
import Sidebar from "./Sidebar";

interface ShellCtx {
  toggleSidebar: () => void;
}
const Ctx = createContext<ShellCtx>({ toggleSidebar: () => {} });
export const useShell = () => useContext(Ctx);

export default function Shell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const loadKbs = useStore((s) => s.loadKbs);
  const loadProjects = useStore((s) => s.loadProjects);

  // load shared data once; collapse by default on small screens
  useEffect(() => {
    if (window.innerWidth < 820) setCollapsed(true);
    loadKbs().catch(() => {});
    loadProjects().catch(() => {});
  }, [loadKbs, loadProjects]);

  return (
    <Ctx.Provider value={{ toggleSidebar: () => setCollapsed((c) => !c) }}>
      <div className={`shell${collapsed ? " collapsed" : ""}`}>
        <Sidebar onNavigate={() => window.innerWidth < 820 && setCollapsed(true)} />
        <div className="main">{children}</div>
      </div>
    </Ctx.Provider>
  );
}
