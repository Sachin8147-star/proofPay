"use client";
import DataTable from "@/components/DataTable";
import { useApi } from "@/lib/api";
import { date, short } from "@/lib/labels";
import { fmtAmt } from "@/lib/chain";

void date; void short; void fmtAmt;
export default function Page() {
  const { data } = useApi<any[]>("/admin/runs", 10000);
  return <div className="space-y-4"><h1>Verification runs</h1><DataTable rows={data} cols={[{ key: "status", label: "Status" }, { key: "repo_url", label: "Repository" }, { key: "res", label: "Result", render: (r) => `${r.passed}/${r.total}` }, { key: "commit_sha", label: "Commit", render: (r) => (r.commit_sha ?? "").slice(0, 7) }, { key: "error", label: "Error" }, { key: "created_at", label: "Started", render: (r) => date(r.created_at) }]} /></div>;
}
