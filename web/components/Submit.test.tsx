import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const form = vi.fn();
vi.mock("@/lib/api", () => ({ apiForm: (...a: any[]) => form(...a) }));
import Submit from "./Submit";

beforeEach(() => { form.mockReset(); form.mockResolvedValue({ run_id: "r" }); });
afterEach(cleanup);
describe("Delivery form", () => {
  it("uploads a zip to the verification endpoint", async () => {
    const done = vi.fn();
    render(<Submit cid="c1" idx={1} deliveryType="software" dry={false} left={5} running={false} onDone={done} />);
    const btn = screen.getByRole("button", { name: /Submit for checking/ }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Zip file/), { target: { files: [new File(["PK"], "site.zip")] } });
    fireEvent.click(btn);
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(form.mock.calls[0][0]).toBe("/contracts/c1/milestones/1/submit");
    const fd: FormData = form.mock.calls[0][1];
    expect(fd.get("source")).toBe("zip");
    expect((fd.get("file") as File).name).toBe("site.zip");
  });
  it("a live-site milestone only offers GitHub or the published address, and needs the address", async () => {
    render(<Submit cid="c1" idx={0} deliveryType="live_site" dry={false} running={false} onDone={() => {}} />);
    expect(screen.queryByRole("tab", { name: "Upload a .zip" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Published website address"), { target: { value: "https://shop.example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /Submit for checking/ }));
    await waitFor(() => expect(form).toHaveBeenCalled());
    expect(form.mock.calls[0][1].get("deploy_url")).toBe("https://shop.example.com");
  });
  it("practice runs use the dry-run endpoint and show server errors", async () => {
    form.mockRejectedValue(new Error("That zip is larger than 25 MB."));
    render(<Submit cid="c1" idx={0} deliveryType="software" dry running={false} onDone={() => {}} />);
    fireEvent.click(screen.getByRole("tab", { name: "GitHub link" }));
    fireEvent.change(screen.getByLabelText("GitHub repository"), { target: { value: "https://github.com/a/b" } });
    fireEvent.click(screen.getByRole("button", { name: "Practice run" }));
    expect((await screen.findByRole("alert")).textContent).toContain("25 MB");
    expect(form.mock.calls[0][0]).toBe("/contracts/c1/milestones/0/dry-run");
  });
});
