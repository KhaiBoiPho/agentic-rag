"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isAuthed } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(isAuthed() ? "/chat" : "/login");
  }, [router]);
  return (
    <div className="center-load" style={{ height: "100%" }}>
      <span className="spinner" />
    </div>
  );
}
