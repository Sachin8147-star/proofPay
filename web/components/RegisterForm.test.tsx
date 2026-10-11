import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const signUp = vi.fn();
const publicApi = vi.fn();
vi.mock("@/lib/supabase", () => ({ supabase: () => ({ auth: { signUp } }) }));
vi.mock("@/lib/api", () => ({ apiPublic: (...a: any[]) => publicApi(...a) }));
import RegisterForm from "./RegisterForm";

function fill() {
  const t = (l: string | RegExp, v: string) => fireEvent.change(screen.getByLabelText(l), { target: { value: v } });
  t("First name", "Sachin"); t(/Gmail/, "s@gmail.com"); t("Phone number", "+91 98765 43210"); t("Where did you hear about us?", "instagram");
  t("Username", "sachin_web"); t("Password", "longpassword1"); t("Repeat password", "longpassword1");
}
beforeEach(() => { signUp.mockReset(); publicApi.mockReset(); publicApi.mockResolvedValue({ available: true }); });
afterEach(cleanup);

describe("Register form", () => {
  it("shows 'Username already exists' when the name is taken and blocks sign-up", async () => {
    publicApi.mockResolvedValue({ available: false, reason: "Username already exists. Pick another." });
    render(<RegisterForm />);
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "taken" } });
    expect(await screen.findByText("Username already exists. Pick another.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Create account" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("rejects bad usernames locally without calling the server", async () => {
    render(<RegisterForm />);
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "a b" } });
    expect(await screen.findByText(/3-24 letters/)).toBeTruthy();
    expect(publicApi).not.toHaveBeenCalled();
  });
  it("marks last name optional and asks for details when 'Other' is chosen", () => {
    render(<RegisterForm />);
    expect(screen.getByText("(optional)")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Where did you hear about us?"), { target: { value: "other" } });
    expect(screen.getByLabelText("Please tell us where")).toBeTruthy();
  });
  it("refuses mismatched passwords", async () => {
    render(<RegisterForm />);
    fill();
    await screen.findByText("Username is available");
    fireEvent.change(screen.getByLabelText("Repeat password"), { target: { value: "different123" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect((await screen.findByRole("alert")).textContent).toContain("do not match");
    expect(signUp).not.toHaveBeenCalled();
  });
  it("sends the whole form as user metadata and tells the user to confirm their email", async () => {
    signUp.mockResolvedValue({ data: { user: { identities: [{}] }, session: null }, error: null });
    render(<RegisterForm />);
    fill();
    await screen.findByText("Username is available");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Check your email")).toBeTruthy();
    expect(signUp.mock.calls[0][0].options.data).toMatchObject({ first_name: "Sachin", handle: "sachin_web", heard_from: "instagram", phone: "+91 98765 43210" });
  });
  it("reports an email that is already registered", async () => {
    signUp.mockResolvedValue({ data: { user: { identities: [] }, session: null }, error: null });
    render(<RegisterForm />);
    fill();
    await screen.findByText("Username is available");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("already has an account"));
  });
});
