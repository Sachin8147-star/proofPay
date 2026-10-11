import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const state: { summary: any; net: any } = { summary: undefined, net: undefined };
vi.mock("@/lib/api", () => ({ useApi: (p: string | null) => ({ data: p === "/me/wallet-summary" ? state.summary : p ? state.net : undefined }) }));
import Wallet from "./page";

const summary = {
  address: "0x" + "a".repeat(40), balance_wei: "2500000000000000000", locked_total: "1.5", incoming_total: "0.5",
  locked: [
    { contract_id: "c1", title: "Bakery site", milestone: "Website", milestone_idx: 0, amount: "1.5", role: "client", status: "funded", why: "You paid up front.", unlock: "Released after the checks pass." },
    { contract_id: "c2", title: "Logo", milestone: "Files", milestone_idx: 0, amount: "0.5", role: "freelancer", status: "funded", why: "Held in escrow while the work is delivered.", unlock: "Released when it passes." }],
  activity: [{ when: "2026-10-05T10:00:00Z", text: "You locked money for \"Bakery site\"", direction: "out", amount: null, tx_hash: "0x" + "1".repeat(64), contract_id: "c1" }],
};
afterEach(cleanup);

describe("Wallet page", () => {
  it("shows real balance, locked and incoming totals", () => {
    state.summary = summary; state.net = { explorer_ok: true, transactions: [] };
    render(<Wallet />);
    expect(screen.getByText("Available now (unlocked)")).toBeTruthy();
    expect(screen.getByText("2.5 MST")).toBeTruthy();
    expect(screen.getByText("Money you locked")).toBeTruthy();
    expect(screen.getByText("Money waiting for you")).toBeTruthy();
    expect(screen.getByText(/locked money for "Bakery site"/)).toBeTruthy();
  });
  it("the (i) button explains why money is locked and when it unlocks", () => {
    state.summary = summary; state.net = { explorer_ok: true, transactions: [] };
    render(<Wallet />);
    expect(screen.queryByText(/You paid up front/)).toBeNull();
    fireEvent.click(screen.getByLabelText("Why is this locked? Bakery site"));
    expect(screen.getByText(/You paid up front/)).toBeTruthy();
    expect(screen.getByText(/Released after the checks pass/)).toBeTruthy();
  });
  it("asks the user to link a wallet when there is none", () => {
    state.summary = { address: null }; state.net = undefined;
    render(<Wallet />);
    expect(screen.getByText("No wallet linked yet")).toBeTruthy();
  });
});
