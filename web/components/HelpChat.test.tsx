import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.fn();
vi.mock("next/navigation", () => ({ usePathname: () => "/wallet" }));
vi.mock("@/lib/api", () => ({ api: (...a: any[]) => apiMock(...a) }));
import HelpChat from "./HelpChat";

beforeEach(() => { Element.prototype.scrollTo = vi.fn(); apiMock.mockReset(); });
afterEach(cleanup);
describe("Help chat", () => {
  it("sends the conversation with the current page and shows the reply", async () => {
    apiMock.mockResolvedValue({ reply: "Paisa escrow mein safe hai." });
    render(<HelpChat />);
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "paisa locked kyun hai?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Paisa escrow mein safe hai.")).toBeTruthy();
    expect(apiMock).toHaveBeenCalledWith("/assistant/chat", { body: { messages: [{ role: "user", content: "paisa locked kyun hai?" }], page: "/wallet" } });
  });
  it("offers starter questions and shows errors", async () => {
    apiMock.mockRejectedValue(new Error("AI is not configured on this server (GEMINI_API_KEY is missing)."));
    render(<HelpChat />);
    fireEvent.click(screen.getByRole("button", { name: "How do I get paid?" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("GEMINI_API_KEY"));
  });
});
