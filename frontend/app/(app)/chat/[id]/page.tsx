'use client';

import ChatView from '@/components/ChatView';

export default function ChatConversationPage({ params }: { params: { id: string } }) {
  return <ChatView conversationId={params.id} />;
}
