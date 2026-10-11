export const CONTRACT_STATUS: Record<string, [string, string]> = {
  draft: ["Not paid yet", "bg-line text-ink"], open: ["Paid, waiting for a worker", "bg-warn-soft text-warn"], active: ["In progress", "bg-brand-soft text-brand"],
  completed: ["Completed", "bg-ok-soft text-ok"], cancelled: ["Cancelled", "bg-line text-mute"],
};
export const MILESTONE_STATUS: Record<string, [string, string]> = {
  pending: ["Not paid", "bg-line text-mute"], funded: ["Money locked", "bg-brand-soft text-brand"], passed: ["Checked, in review window", "bg-ok-soft text-ok"],
  disputed: ["Disputed", "bg-bad-soft text-bad"], released: ["Paid", "bg-ok-soft text-ok"], refunded: ["Refunded", "bg-line text-mute"],
};
export const KIND_LABEL: Record<string, string> = {
  file_exists: "File exists", file_contains: "File contains", http: "Check on the published site", command: "Run command in sandbox",
  ai_review: "AI review (must quote proof)", manual: "Buyer confirms", hidden: "Hidden test",
};
export const DELIVERY: Record<string, { label: string; hint: string }> = {
  software: { label: "Software / files", hint: "Delivered as a .zip file or a GitHub link and checked automatically." },
  live_site: { label: "Published website", hint: "Delivered as a live website address. We open it and check it." },
  product: { label: "Physical product", hint: "Seller ships it. You press “I received it” to release the money." },
};
export const HEARD = [["instagram", "Instagram"], ["facebook", "Facebook"], ["youtube", "YouTube"], ["x", "X (Twitter)"], ["linkedin", "LinkedIn"], ["whatsapp", "WhatsApp"], ["google", "Google search"], ["friend", "A friend"], ["other", "Other"]] as const;
export const short = (h?: string | null, n = 6) => (h ? `${h.slice(0, n + 2)}…${h.slice(-4)}` : "");
export const date = (s?: string | null) => (s ? new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "");
