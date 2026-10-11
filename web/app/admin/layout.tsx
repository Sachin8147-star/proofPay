"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { NavLink } from "@/components/ui";
import WalletBar from "@/components/WalletBar";
import { api, useApi } from "@/lib/api";
import { supabase } from "@/lib/supabase";

const NAV: [string, string][] = [["/admin", "Overview"], ["/admin/disputes", "Disputes"], ["/admin/contracts", "Contracts"], ["/admin/notifications", "Notifications"], ["/admin/runs", "Verification runs"], ["/admin/users", "Users"], ["/admin/audit", "Audit log"]];

export default function AdminShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [state, setState] = useState<"loading" | "ok" | "denied">("loading");
  const isLogin = path.startsWith("/admin/login");

  useEffect(() => {
    if (isLogin) return;
    supabase().auth.getSession().then(async ({ data }) => {
      if (!data.session) return router.replace("/admin/login");
      try { await api("/admin/overview"); setState("ok"); } catch { setState("denied"); }
    });
  }, [isLogin, router]);

  const { data: notes } = useApi<any>(state === "ok" ? "/notifications" : null, 10000);
  if (isLogin) return <>{children}</>;
  if (state === "loading") return null;
  if (state === "denied")
    return (
      <main className="mx-auto max-w-sm px-5 py-24 text-center">
        <h1>Not authorized</h1><p className="mt-2 text-sm text-mute">This account does not have admin access.</p>
        <button className="btn-ghost mt-5" onClick={() => supabase().auth.signOut().then(() => router.replace("/admin/login"))}>Sign out</button>
      </main>
    );
  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-5 md:flex-row">
      <aside className="w-full shrink-0 space-y-6 md:w-56">
        <Link href="/admin" className="block text-lg font-bold">ProofPay admin</Link>
        <nav className="space-y-1">{NAV.map(([h, l]) => <NavLink key={h} href={h} active={h === path} badge={h === "/admin/notifications" ? notes?.unread : undefined}>{l}</NavLink>)}</nav>
        <div className="panel p-3"><p className="mb-2 text-xs text-mute">Arbitrator wallet</p><WalletBar /></div>
        <button className="link text-sm" onClick={() => supabase().auth.signOut().then(() => router.replace("/admin/login"))}>Sign out</button>
      </aside>
      <main className="min-w-0 flex-1 pb-16">{children}</main>
    </div>
  );
}
