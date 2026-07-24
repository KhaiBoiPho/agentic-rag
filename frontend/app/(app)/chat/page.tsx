'use client';

import { useState } from 'react';
import ChatView from '@/components/ChatView';

export default function ChatIndexPage() {
  const [id] = useState(() => crypto.randomUUID());
  return <ChatView conversationId={id} />;
}
