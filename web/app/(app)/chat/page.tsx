"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// Landing on /chat mints a fresh conversation UUID and redirects to it.
export default function ChatIndex() {
  const router = useRouter();
  useEffect(() => {
    router.replace(`/chat/${crypto.randomUUID()}`);
  }, [router]);
  return (
    <div className="center-load">
      <span className="spinner" />
    </div>
  );
}
