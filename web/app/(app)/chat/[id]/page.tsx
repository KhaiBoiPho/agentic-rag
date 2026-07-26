"use client";

import { use } from "react";
import ChatView from "@/components/chat/ChatView";

export default function ChatConversation({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <ChatView key={id} conversationId={id} />;
}
