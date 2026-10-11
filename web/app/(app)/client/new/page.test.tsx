import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const apiMock = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api", () => ({ api: (...a: any[]) => apiMock(...a), useApi: () => ({ data: { wallet: "0x" + "a".repeat(40) } }) }));
import NewContract from "./page";

async function toEditStep() {
  fireEvent.click(screen.getByRole("button", { name: "Start blank" }));
  await screen.findByText("Review the contract");
}
beforeEach(() => { apiMock.mockReset(); push.mockReset(); });
afterEach(cleanup);

describe("New contract wizard", () => {
  it("needs a real description before explaining or building checks", () => {
    render(<NewContract />);
    const explain = screen.getByRole("button", { name: "Explain my idea" }) as HTMLButtonElement;
    expect(explain.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Describe what you want"), { target: { value: "Mujhe ek bakery website chahiye" } });
    expect(explain.disabled).toBe(false);
  });

  it("shows the AI's explanation, suggestions and how the work is checked", async () => {
    apiMock.mockResolvedValue({ title: "Bakery site", understood: "You want a bakery website with ordering.", deliverables: [{ title: "Website", type: "live_site", detail: "menu and orders" }],
      suggestions: ["Add opening hours"], questions: ["Which city?"], how_checked: ["We open the published site and look for an order form."] });
    render(<NewContract />);
    fireEvent.change(screen.getByLabelText("Describe what you want"), { target: { value: "Mujhe ek bakery website chahiye" } });
    fireEvent.click(screen.getByRole("button", { name: "Explain my idea" }));
    expect(await screen.findByText("You want a bakery website with ordering.")).toBeTruthy();
    expect(apiMock.mock.calls[0][0]).toBe("/ai/idea");
    expect(screen.getByText("Add opening hours")).toBeTruthy();
    expect(screen.getByText("Which city?")).toBeTruthy();
    expect(screen.getByText(/look for an order form/)).toBeTruthy();
  });

  it("looks up the worker's username and explains a missing wallet", async () => {
    apiMock.mockResolvedValue({ handle: "ravi", name: "Ravi", has_wallet: false, is_you: false });
    render(<NewContract />);
    fireEvent.change(screen.getByLabelText("Worker's username"), { target: { value: "@Ravi" } });
    expect(await screen.findByText(/has not connected a wallet/)).toBeTruthy();
    expect(apiMock).toHaveBeenCalledWith("/users/ravi");
    expect((screen.getByRole("button", { name: "Build the checks" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("sends the edited requirements to the checker and lists what it finds", async () => {
    apiMock.mockResolvedValue({ ai: false, issues: [
      { milestone: 0, requirement: 0, severity: "warn", issue: '"modern" is subjective.', suggestion: "State a measurable outcome." },
      { milestone: 0, requirement: null, severity: "info", issue: "Only files are checked.", suggestion: "Add a command test." }] });
    render(<NewContract />);
    await toEditStep();
    fireEvent.change(screen.getAllByLabelText("Requirement")[0], { target: { value: "Modern design" } });
    fireEvent.click(screen.getByRole("button", { name: "Check my requirements" }));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
    const [path, opts] = apiMock.mock.calls[0];
    expect(path).toBe("/compile/review");
    expect(opts.body.milestones[0].requirements[0]).toMatchObject({ title: "Modern design", kind: "ai_review", hidden: false });
    expect(await screen.findByText(/"modern" is subjective/)).toBeTruthy();
    expect(screen.getByText("Fix")).toBeTruthy();
    expect(screen.getByText(/Part 1, Modern design\./)).toBeTruthy();
  });

  it("a physical product part is confirmed by the buyer and has no automatic checks", async () => {
    render(<NewContract />);
    await toEditStep();
    fireEvent.click(screen.getByRole("button", { name: "Add physical product" }));
    const selects = screen.getAllByLabelText("Checked by") as HTMLSelectElement[];
    expect(selects[1].disabled).toBe(true);
    expect(selects[1].value).toBe("manual");
    expect(screen.getAllByText(/press “I received it”/).length).toBeGreaterThan(0);
  });

  it("keeps the save button disabled until there is a title and a positive total, then saves an open job", async () => {
    apiMock.mockResolvedValue({ id: "c1" });
    render(<NewContract />);
    await toEditStep();
    const save = screen.getByRole("button", { name: "Save and go to payment" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Shop site" } });
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Part 1: what is delivered"), { target: { value: "Shop website" } });
    fireEvent.change(screen.getByLabelText("Requirement"), { target: { value: "Includes the requested shop pages" } });
    fireEvent.change(screen.getByLabelText(/What must be true/), { target: { value: "The delivered site includes the requested shop pages" } });
    fireEvent.change(screen.getByLabelText(/Amount/), { target: { value: "2.5" } });
    expect(save.disabled).toBe(false);
    expect(screen.getByText(/open job/)).toBeTruthy();
    fireEvent.click(save);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/client/c1"));
    expect(apiMock.mock.calls[0][1].body).toMatchObject({ title: "Shop site", freelancer_username: null });
  });
});
