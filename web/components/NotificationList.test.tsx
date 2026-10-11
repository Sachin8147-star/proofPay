import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const state: { data: any; error: any; api: ReturnType<typeof vi.fn>; mutate: ReturnType<typeof vi.fn> } = { data: undefined, error: undefined, api: vi.fn(), mutate: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api", () => ({ api: (...a: any[]) => state.api(...a), useApi: () => ({ data: state.data, error: state.error, mutate: state.mutate }) }));
import NotificationList from "./NotificationList";

const items = [
  { id: "n1", kind: "invite", title: "New contract to review", body: "Shop API", link: "/freelancer/c1", read_at: null, created_at: "2026-10-05T10:00:00Z" },
  { id: "n2", kind: "payment", title: "Payment released: 1.5 MST", body: "", link: "/freelancer/c1", read_at: "2026-10-05T11:00:00Z", created_at: "2026-10-05T09:00:00Z" },
];
beforeEach(() => { state.error = undefined; state.api = vi.fn().mockResolvedValue({}); state.mutate = vi.fn(); state.data = { items, unread: 1 }; });
afterEach(cleanup);

describe("NotificationList", () => {
  it("shows loading, error and empty states", () => {
    state.data = undefined; const r = render(<NotificationList />);
    expect(screen.getByText("Loading…")).toBeTruthy();
    state.error = new Error("Session expired"); r.rerender(<NotificationList />);
    expect(screen.getByText("Session expired")).toBeTruthy();
    state.error = undefined; state.data = { items: [], unread: 0 }; r.rerender(<NotificationList />);
    expect(screen.getByText("Nothing yet")).toBeTruthy();
  });
  it("marks unread items and hides 'Mark all' when everything is read", () => {
    const r = render(<NotificationList />);
    expect(screen.getByLabelText("unread")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Mark all as read" })).toBeTruthy();
    state.data = { items: items.map((i) => ({ ...i, read_at: "x" })), unread: 0 }; r.rerender(<NotificationList />);
    expect(screen.queryByRole("button", { name: "Mark all as read" })).toBeNull();
  });
  it("opening an unread item marks it read, then navigates to its link", async () => {
    render(<NotificationList />);
    fireEvent.click(screen.getByText("New contract to review"));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/freelancer/c1"));
    expect(state.api).toHaveBeenCalledWith("/notifications/read", { body: { ids: ["n1"] } });
    expect(state.mutate).toHaveBeenCalled();
  });
  it("opening an already-read item only navigates", async () => {
    render(<NotificationList />);
    fireEvent.click(screen.getByText("Payment released: 1.5 MST"));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/freelancer/c1"));
    expect(state.api).not.toHaveBeenCalled();
  });
  it("'Mark all as read' sends an empty body (all of this user's unread)", async () => {
    render(<NotificationList />);
    fireEvent.click(screen.getByRole("button", { name: "Mark all as read" }));
    await waitFor(() => expect(state.api).toHaveBeenCalledWith("/notifications/read", { body: {} }));
  });
});
