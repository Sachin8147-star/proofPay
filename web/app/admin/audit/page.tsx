"use client";
import DataTable from "@/components/DataTable";
import { useApi } from "@/lib/api";
import { date, short } from "@/lib/labels";
import { fmtAmt } from "@/lib/chain";

void date; void short; void fmtAmt;
export default function Page() {
  const { data } = useApi<any[]>("/admin/audit", 10000);
  return <div className="space-y-4"><h1>Audit log</h1><DataTable rows={data} cols={[{ key: "created_at", label: "When", render: (r) => date(r.created_at) }, { key: "action", label: "Action" }, { key: "entity", label: "Entity" }, { key: "entity_id", label: "ID", render: (r) => short(r.entity_id, 4) }, { key: "meta", label: "Details", render: (r) => <span className="font-mono text-xs">{JSON.stringify(r.meta)}</span> }]} /></div>;
}
