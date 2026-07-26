"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isAuthed } from "@/lib/auth";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ok, setOk] = useState(false);

  useEffect(() => {
    if (!isAuthed()) {
      router.replace("/login");
    } else {
      setOk(true);
    }
  }, [router]);

  if (!ok) {
    return (
      <div className="center-load" style={{ height: "100%" }}>
        <span className="spinner" />
      </div>
    );
  }
  return <>{children}</>;
}
