"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { NavLink } from "@/components/ui";
import ShareId from "@/components/ShareId";
import WalletBar from "@/components/WalletBar";
import { useApi } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const auth = supabase().auth;
    auth.getSession().then(({ data }) => (data.session ? setReady(true) : router.replace(`/login?next=${path}`)));
    const { data: sub } = auth.onAuthStateChange((_e, s) => !s && router.replace("/login"));
    return () => sub.subscription.unsubscribe();
  }, [router, path]);

  const { data: notes } = useApi<any>(ready ? "/notifications" : null, 10000);
  const { data: me } = useApi<any>(ready ? "/me" : null);
  if (!ready) return null;
  const nav: [string, string][] = [["/client", "My contracts"], ["/client/new", "New contract"], ["/freelancer", "My work"], ["/jobs", "Find work"], ["/notifications", "Notifications"], ["/wallet", "Wallet"], ["/help", "Help"], ["/settings", "Profile"]];
  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-5 md:flex-row">
      <aside className="w-full shrink-0 space-y-6 md:w-56">
        <Link href="/" className="block text-lg font-bold">ProofPay</Link>
        <nav className="space-y-1">{nav.map(([h, l]) => <NavLink key={h} href={h} active={h === path || (h !== "/client" && path.startsWith(h) && h !== "/client/new") || (h === "/client" && /^\/client\/[^n]/.test(path))} badge={h === "/notifications" ? notes?.unread : undefined}>{l}</NavLink>)}</nav>
        {me?.handle && <div className="panel p-3"><ShareId handle={me.handle} /></div>}
        <div className="panel p-3"><WalletBar /></div>
        <button className="link text-sm" onClick={() => supabase().auth.signOut()}>Sign out</button>
      </aside>
      <main className="min-w-0 flex-1 pb-16">{children}</main>
    </div>
  );
}
