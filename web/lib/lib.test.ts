import { describe, expect, it } from "vitest";
import { errorText } from "./errors";
import { addrUrl, fmtAmt, fmtWei, txUrl } from "./format";
import { normalizeUsername, usernameProblem } from "./username";
import { CONTRACT_STATUS, MILESTONE_STATUS, short } from "./labels";

describe("format", () => {
  it("formats amounts and wei with the symbol", () => {
    expect(fmtAmt("1.5")).toBe("1.5 MST");
    expect(fmtAmt(0)).toBe("0 MST");
    expect(fmtWei(1_500_000_000_000_000_000n)).toBe("1.5 MST");
    expect(fmtWei("1")).toBe("0 MST"); // 1 wei rounds away at 6 decimals
  });
  it("builds explorer links", () => {
    expect(txUrl("0xabc")).toBe("https://testnet.mstscan.com/tx/0xabc");
    expect(addrUrl("0xdef")).toBe("https://testnet.mstscan.com/address/0xdef");
  });
});

describe("errorText", () => {
  it("passes strings through", () => expect(errorText("Not found", "x")).toBe("Not found"));
  it("flattens FastAPI validation errors", () =>
    expect(errorText([{ loc: ["body", "milestones", 0, "amount"], msg: "must be > 0" }, { loc: ["body", "title"], msg: "too short" }], "x")).toBe("milestones.0.amount: must be > 0; title: too short"));
  it("falls back for unknown shapes", () => expect(errorText(undefined, "Bad Gateway")).toBe("Bad Gateway"));
});

describe("labels", () => {
  it("shortens hashes and addresses", () => {
    expect(short("0x1234567890abcdef1234567890abcdef12345678", 4)).toBe("0x1234…5678");
    expect(short(null)).toBe("");
  });
  it("has a label for every status the backend can send", () => {
    for (const s of ["draft", "open", "active", "completed", "cancelled"]) expect(CONTRACT_STATUS[s]).toBeTruthy();
    for (const s of ["pending", "funded", "passed", "disputed", "released", "refunded"]) expect(MILESTONE_STATUS[s]).toBeTruthy();
  });
});

describe("username rules", () => {
  it("normalizes and validates like the server", () => {
    expect(normalizeUsername(" @Sachin_Web ")).toBe("sachin_web");
    expect(usernameProblem("sachin_web")).toBeNull();
    expect(usernameProblem("ab")).toMatch(/3-24/);
    expect(usernameProblem("has space")).toMatch(/3-24/);
    expect(usernameProblem("admin")).toMatch(/reserved/);
  });
});
