'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api } from './api';
import { DEFAULT_MODEL } from './types';
import type { ChatMessage, ConversationMeta, KBResponse, ProjectResponse } from './types';

interface AppState {
  kbs: KBResponse[];
  projects: ProjectResponse[];
  conversations: ConversationMeta[];
  activeKbId: string | null;
  activeProjectId: string | null;
  loadedOnce: boolean;

  messagesByConversation: Record<string, ChatMessage[]>;
  setMessages: (conversationId: string, messages: ChatMessage[]) => void;

  model: string;
  temperature: number;
  maxTokens: number;

  refreshKbs: () => Promise<void>;
  refreshProjects: () => Promise<void>;
  refreshAll: () => Promise<void>;
  setActiveKb: (id: string | null) => void;
  setActiveProject: (id: string | null) => void;

  upsertConversation: (id: string, title: string) => void;
  removeConversation: (id: string) => void;

  setModel: (m: string) => void;
  setTemperature: (t: number) => void;
  setMaxTokens: (t: number) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      kbs: [],
      projects: [],
      conversations: [],
      activeKbId: null,
      activeProjectId: null,
      loadedOnce: false,

      messagesByConversation: {},
      setMessages: (conversationId, messages) =>
        set({ messagesByConversation: { ...get().messagesByConversation, [conversationId]: messages } }),

      model: DEFAULT_MODEL,
      temperature: 0.7,
      maxTokens: 2048,

      refreshKbs: async () => {
        const kbs = await api.get<KBResponse[]>('/api/v1/kb');
        set({ kbs });
      },
      refreshProjects: async () => {
        const projects = await api.get<ProjectResponse[]>('/api/v1/projects');
        set({ projects });
      },
      refreshAll: async () => {
        await Promise.all([get().refreshKbs(), get().refreshProjects()]);
        set({ loadedOnce: true });
      },
      setActiveKb: (id) => set({ activeKbId: id, activeProjectId: id ? null : get().activeProjectId }),
      setActiveProject: (id) => set({ activeProjectId: id, activeKbId: id ? null : get().activeKbId }),

      upsertConversation: (id, title) => {
        const list = get().conversations.filter((c) => c.id !== id);
        set({
          conversations: [{ id, title, updated_at: Math.floor(Date.now() / 1000) }, ...list].slice(0, 100),
        });
      },
      removeConversation: (id) => {
        set({ conversations: get().conversations.filter((c) => c.id !== id) });
      },

      setModel: (m) => set({ model: m }),
      setTemperature: (t) => set({ temperature: t }),
      setMaxTokens: (t) => set({ maxTokens: t }),
    }),
    {
      name: 'agentic-app-store',
      partialize: (s) => ({
        conversations: s.conversations,
        model: s.model,
        temperature: s.temperature,
        maxTokens: s.maxTokens,
      }),
    },
  ),
);
