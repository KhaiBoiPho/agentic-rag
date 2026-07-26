import { create } from "zustand";
import { api } from "./api";
import { DEFAULT_MODEL } from "./models";
import type { AppSettings, Conversation, KB, Project } from "./types";

const SETTINGS_KEY = "cot.settings";
const CONV_KEY = "cot.conversations";
const LANG_KEY = "cot.lang";

type Lang = "vi" | "en";

function loadLang(): Lang {
  if (typeof window === "undefined") return "vi";
  const v = localStorage.getItem(LANG_KEY);
  return v === "en" ? "en" : "vi";
}

function loadSettings(): AppSettings {
  if (typeof window !== "undefined") {
    try {
      const raw = localStorage.getItem(SETTINGS_KEY);
      if (raw) return { ...defaultSettings(), ...JSON.parse(raw) };
    } catch {
      /* ignore */
    }
  }
  return defaultSettings();
}
function defaultSettings(): AppSettings {
  return { model: DEFAULT_MODEL, temperature: 0.7, max_tokens: 2048, top_k: 5 };
}

function loadConversations(): Conversation[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(CONV_KEY) || "[]");
  } catch {
    return [];
  }
}
function saveConversations(list: Conversation[]) {
  if (typeof window !== "undefined") localStorage.setItem(CONV_KEY, JSON.stringify(list.slice(0, 50)));
}

interface Store {
  kbs: KB[];
  projects: Project[];
  conversations: Conversation[];
  settings: AppSettings;
  lang: Lang;
  // active retrieval scope for chat
  activeKbId: string | null;
  activeProjectId: string | null;

  loadKbs: () => Promise<void>;
  loadProjects: () => Promise<void>;
  setActiveKb: (id: string | null) => void;
  setActiveProject: (id: string | null) => void;
  setSettings: (s: Partial<AppSettings>) => void;
  setLang: (l: Lang) => void;

  upsertConversation: (c: Conversation) => void;
  removeConversation: (id: string) => void;
  clearConversations: () => void;
}

export const useStore = create<Store>((set, get) => ({
  kbs: [],
  projects: [],
  conversations: loadConversations(),
  settings: loadSettings(),
  lang: loadLang(),
  activeKbId: null,
  activeProjectId: null,

  loadKbs: async () => {
    const kbs = await api.get<KB[]>("/api/v1/kb/");
    set({ kbs });
  },
  loadProjects: async () => {
    const projects = await api.get<Project[]>("/api/v1/projects");
    set({ projects });
  },
  setActiveKb: (id) => set({ activeKbId: id, activeProjectId: null }),
  setActiveProject: (id) => set({ activeProjectId: id, activeKbId: null }),
  setSettings: (s) => {
    const next = { ...get().settings, ...s };
    if (typeof window !== "undefined") localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
    set({ settings: next });
  },

  setLang: (l) => {
    if (typeof window !== "undefined") localStorage.setItem(LANG_KEY, l);
    set({ lang: l });
  },

  upsertConversation: (c) => {
    const rest = get().conversations.filter((x) => x.id !== c.id);
    const next = [c, ...rest];
    saveConversations(next);
    set({ conversations: next });
  },
  removeConversation: (id) => {
    const next = get().conversations.filter((x) => x.id !== id);
    saveConversations(next);
    set({ conversations: next });
  },
  clearConversations: () => {
    saveConversations([]);
    set({ conversations: [] });
  },
}));
