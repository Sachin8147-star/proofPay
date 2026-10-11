"""Vague-requirement checker: flags requirements that cannot be settled objectively, before anyone signs.
Deterministic rules always run; the AI pass (compiler.review_ai) is an optional extra."""
import re

from . import verifier

VAGUE = re.compile(r"\b(modern|nice|clean|good|great|beautiful|pretty|professional|fast|quick|intuitive|user[- ]friendly|robust|scalable|seamless|high[- ]quality|polished|best|easy|simple|optimi[sz]ed|improved?|properly|correctly|smooth|responsive|well)\b", re.I)
BEHAVIOR = re.compile(r"\b(login|log in|sign ?up|auth\w*|cart|checkout|payment|search|api|endpoints?|crud|database|upload|email|notifications?|dashboard|filter|sort|pagination)\b", re.I)
ALWAYS_OK = re.compile(r"^(true|exit 0|:|pwd|echo\b.*|ls\b.*)$|\|\|\s*true|;\s*true\s*$", re.I)
WEAK = ("file_exists", "file_contains")


def _issue(mi, rj, sev, issue, suggestion):
    return {"milestone": mi, "requirement": rj, "severity": sev, "issue": issue, "suggestion": suggestion}


def review(milestones: list[dict]) -> list[dict]:
    out, seen = [], {}
    for i, m in enumerate(milestones):
        reqs = m.get("requirements", [])
        if reqs and all(r.get("hidden") for r in reqs):
            out.append(_issue(i, None, "warn", "Every test in this milestone is hidden, so the freelancer cannot see or dry-run any of them.",
                              "Show at least the basic tests and keep only the edge-case ones hidden."))
        if reqs and all(r.get("kind") in WEAK for r in reqs):
            out.append(_issue(i, None, "info", "This milestone only checks files, not behavior.", "Add a command test (pytest, npm test) or an HTTP check."))
        for j, r in enumerate(reqs):
            kind, spec, title = r.get("kind"), r.get("spec") or {}, r.get("title") or ""
            key = title.strip().lower()
            if key and key in seen:
                out.append(_issue(i, j, "info", "Another requirement has the same title.", "Make each requirement distinct so results are unambiguous."))
            seen[key] = True
            try:
                spec = verifier.validate_spec(kind, spec)
            except Exception as e:
                out.append(_issue(i, j, "warn", f"This test is not valid: {e}", "Fix the test settings before saving."))
                continue
            if kind == "command" and ALWAYS_OK.search(spec["cmd"].strip()):
                out.append(_issue(i, j, "warn", "This command always succeeds, so the requirement would pass without any work.", "Run a real test suite, e.g. pytest -q or npm test."))
            if kind == "file_contains" and len(spec["pattern"].strip("^$.*+?()[]|\\ ")) < 4:
                out.append(_issue(i, j, "warn", "The pattern is so loose that almost any file would match.", "Match something specific, such as a function or route name."))
            if kind == "http" and spec["path"] == "/" and not spec.get("expect_contains") and spec["expect_status"] == 200:
                out.append(_issue(i, j, "info", "A home page returning 200 only proves the site is online.", "Also check that the response contains expected content."))
            if kind == "http" and spec["expect_status"] >= 500:
                out.append(_issue(i, j, "warn", "This test expects a server error status.", "Expect a 2xx or a deliberate 4xx such as 401."))
            if kind in WEAK and BEHAVIOR.search(title):
                out.append(_issue(i, j, "warn", "A file check cannot prove this behavior works.", "Verify it with a command test or an HTTP check against the deployed site."))
                continue
            v = VAGUE.search(title + " " + (r.get("criteria") or ""))
            if not v:
                continue
            weak = kind in WEAK
            out.append(_issue(i, j, "warn" if weak else "info",
                              f'"{v.group(0)}" is subjective' + (", and a file check cannot measure it." if weak else "; make sure the test really measures it."),
                              'State a measurable outcome, e.g. "GET /api/products returns 200 and a JSON list".'))
    order = lambda x: (0 if x["severity"] == "warn" else 1, x["milestone"], -1 if x["requirement"] is None else x["requirement"])
    return sorted(out, key=order)
