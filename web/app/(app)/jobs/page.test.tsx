import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const seen: string[] = [];
let rows: any[] | undefined;
vi.mock("@/lib/api", () => ({ useApi: (p: string) => { seen.push(p); return { data: rows }; } }));
import Jobs from "./page";

afterEach(() => { cleanup(); seen.length = 0; });
describe("Open jobs board", () => {
  it("lists paid jobs with the amount, types and poster", () => {
    rows = [{ id: "j1", title: "Bakery website", description: "Menu and orders", total: "3", types: ["live_site", "product"], milestones: [{}, {}], earliest_deadline: null, poster: { handle: "asha" } }];
    render(<Jobs />);
    expect(screen.getByText("Bakery website")).toBeTruthy();
    expect(screen.getByText("3 MST")).toBeTruthy();
    expect(screen.getByText("Published website")).toBeTruthy();
    expect(screen.getByText("Physical product")).toBeTruthy();
    expect(screen.getByText("by @asha")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Bakery website/ }).getAttribute("href")).toBe("/jobs/j1");
  });
  it("searches through the API and explains an empty board", () => {
    rows = [];
    render(<Jobs />);
    expect(screen.getByText("No open jobs right now")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Search jobs"), { target: { value: "logo" } });
    expect(seen.at(-1)).toBe("/jobs?q=logo");
  });
});
