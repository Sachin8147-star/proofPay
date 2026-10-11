import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const state: { data: any; api: ReturnType<typeof vi.fn>; mutate: ReturnType<typeof vi.fn> } = { data: undefined, api: vi.fn(), mutate: vi.fn() };
vi.mock("@/lib/api", () => ({ api: (...a: any[]) => state.api(...a), useApi: () => ({ data: state.data, mutate: state.mutate }) }));
import Chat from "./Chat";

const msgs = [
  { id: "1", mine: false, name: "Freelancer", body: "Hi, quick question about milestone 2", created_at: "2026-10-05T10:00:00Z" },
  { id: "2", mine: true, name: "Client", body: "Sure, go ahead", created_at: "2026-10-05T10:01:00Z" },
];
beforeEach(() => { Element.prototype.scrollTo = vi.fn(); state.api = vi.fn().mockResolvedValue({}); state.mutate = vi.fn().mockResolvedValue(undefined); state.data = msgs; });
afterEach(cleanup);

describe("Chat", () => {
  it("shows a loading state, then an empty state with guidance", () => {
    state.data = undefined; const { rerender } = render(<Chat id="c1" />);
    expect(screen.getByText("Loading…")).toBeTruthy();
    state.data = []; rerender(<Chat id="c1" />);
    expect(screen.getByText(/No messages yet/)).toBeTruthy();
  });
  it("renders both sides, labelling your own messages 'You'", () => {
    render(<Chat id="c1" />);
    expect(screen.getByText("Hi, quick question about milestone 2")).toBeTruthy();
    expect(screen.getByText(/^You ·/)).toBeTruthy();
    expect(screen.getByText(/^Freelancer ·/)).toBeTruthy();
  });
  it("renders message text as plain text, never as HTML", () => {
    state.data = [{ ...msgs[0], body: "<img src=x onerror=alert(1)>" }];
    const { container } = render(<Chat id="c1" />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeTruthy();
  });
  it("marks messages read when the other person's messages are on screen", async () => {
    render(<Chat id="c1" />);
    await waitFor(() => expect(state.api).toHaveBeenCalledWith("/contracts/c1/read", { method: "POST" }));
  });
  it("does not call read when there is nothing from the other person", () => {
    state.data = [msgs[1]]; render(<Chat id="c1" />);
    expect(state.api).not.toHaveBeenCalled();
  });
  it("sends trimmed text, clears the box, and refreshes", async () => {
    render(<Chat id="c1" />);
    const box = screen.getByLabelText("Write a message") as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "  Looks good  " } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(state.api).toHaveBeenCalledWith("/contracts/c1/messages", { body: { body: "Looks good" } }));
    await waitFor(() => expect(box.value).toBe(""));
    expect(state.mutate).toHaveBeenCalled();
  });
  it("sends on Enter but not on Shift+Enter", async () => {
    render(<Chat id="c1" />);
    const box = screen.getByLabelText("Write a message");
    fireEvent.change(box, { target: { value: "one" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(state.api).not.toHaveBeenCalledWith("/contracts/c1/messages", expect.anything());
    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() => expect(state.api).toHaveBeenCalledWith("/contracts/c1/messages", { body: { body: "one" } }));
  });
  it("disables Send for blank text and keeps the draft when sending fails", async () => {
    render(<Chat id="c1" />);
    const send = screen.getByRole("button", { name: "Send" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    const box = screen.getByLabelText("Write a message") as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "   " } });
    expect(send.disabled).toBe(true);
    state.api = vi.fn().mockRejectedValue(new Error("You're sending messages too fast. Wait a moment."));
    fireEvent.change(box, { target: { value: "hello" } });
    fireEvent.click(send);
    expect((await screen.findByRole("alert")).textContent).toContain("too fast");
    expect(box.value).toBe("hello");
  });
});
