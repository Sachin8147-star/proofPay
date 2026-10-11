"""Verification engine: takes the delivered work (a GitHub commit, an uploaded zip and/or a published site),
runs the contract's checks, and returns evidence. AI checks only count when their quote is found in the files."""
import fnmatch
import hashlib
import io
import ipaddress
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from . import ai, compiler
from .config import settings

KINDS = ("file_exists", "file_contains", "http", "command", "ai_review", "manual")
MAX_REPO_BYTES = 60 * 1024 * 1024
MAX_ZIP_FILES, MAX_ZIP_UNPACKED = 5000, 200 * 1024 * 1024
TEXT_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".scss", ".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".ini", ".env.example",
            ".java", ".kt", ".go", ".rs", ".rb", ".php", ".c", ".cpp", ".h", ".cs", ".sql", ".sh", ".vue", ".svelte", ".xml", ".gradle", ".swift", ".dart", ".csv"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build", ".next", "vendor", "target", ".idea", ".vscode"}
INJECTION = re.compile(r"(ignore (all|any|the|previous|prior)|disregard|you are (a|the|an) (judge|ai|assistant|model|grader)|as an ai|mark (this|it|the claim) as|set\s+met|[\"']met[\"']\s*:\s*true|"
                       r"the claim is (met|true|satisfied)|system prompt|respond with)", re.I)


class InfraError(Exception):
    """Our infrastructure failed (not the freelancer's work) -> no attestation is sent."""


def validate_spec(kind: str, spec: dict) -> dict:
    """Raises ValueError for malformed test specs; returns a normalized copy."""
    s = dict(spec or {})
    if kind in ("file_exists", "file_contains"):
        p = str(s.get("path", ""))
        if not p or p.startswith("/") or ".." in Path(p).parts:
            raise ValueError("path must be a relative path inside the repo")
        s["path"] = p
        if kind == "file_contains":
            pat = str(s.get("pattern", ""))
            if not pat or len(pat) > 200:
                raise ValueError("pattern is required (max 200 chars)")
            re.compile(pat)
    elif kind == "http":
        s["method"] = str(s.get("method", "GET")).upper()
        if s["method"] not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            raise ValueError("unsupported HTTP method")
        if not str(s.get("path", "")).startswith("/"):
            raise ValueError("http path must start with /")
        s["expect_status"] = int(s.get("expect_status", 200))
    elif kind == "command":
        if not str(s.get("cmd", "")).strip():
            raise ValueError("cmd is required")
        s["image"] = s.get("image") or settings.sandbox_images.split(",")[0]
        if s["image"] not in settings.sandbox_images.split(","):
            raise ValueError(f"image must be one of {settings.sandbox_images}")
        s["timeout"] = min(int(s.get("timeout", 120)), 300)
    elif kind == "ai_review":
        claim = str(s.get("claim", "")).strip()
        if not 5 <= len(claim) <= 500:
            raise ValueError("claim is required (5-500 characters)")
        paths = s.get("paths") or []
        if not isinstance(paths, list) or len(paths) > 5 or any(not isinstance(x, str) or len(x) > 100 or x.startswith("/") or ".." in x for x in paths):
            raise ValueError("paths must be up to 5 relative patterns")
        s = {"claim": claim, "paths": paths}
    elif kind == "manual":
        s = {"note": str(s.get("note", ""))[:300]}
    else:
        raise ValueError(f"unknown test kind {kind}")
    return s


def safe_url(url: str) -> str:
    """SSRF guard: only public http(s) hosts."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("deploy URL must be http(s)")
    try:
        infos = socket.getaddrinfo(u.hostname, None)
    except socket.gaierror:
        raise ValueError("That web address could not be found. Check the spelling.")
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError("deploy URL must point to a public host")
    return url.rstrip("/")


# ---------- repo fetch ----------

def parse_repo(url: str) -> tuple[str, str]:
    m = re.match(r"^https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$", url.strip())
    if not m:
        raise ValueError("Repository must be a github.com URL")
    return m.group(1), m.group(2)


def _gh_headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "proofpay"}
    if settings.github_token:
        h["Authorization"] = f"Bearer {settings.github_token}"
    return h


def resolve_commit(repo_url: str, ref: str | None) -> str:
    owner, repo = parse_repo(repo_url)
    r = httpx.get(f"https://api.github.com/repos/{owner}/{repo}/commits/{ref or 'HEAD'}", headers=_gh_headers(), timeout=20)
    if r.status_code == 404:
        raise InfraError("Repository or commit not found (private repos need GITHUB_TOKEN access).")
    if r.status_code != 200:
        raise InfraError(f"GitHub returned {r.status_code}")
    return r.json()["sha"]


def download(repo_url: str, sha: str, dest: Path) -> Path:
    owner, repo = parse_repo(repo_url)
    buf = io.BytesIO()
    with httpx.stream("GET", f"https://api.github.com/repos/{owner}/{repo}/tarball/{sha}", headers=_gh_headers(),
                      follow_redirects=True, timeout=60) as r:
        if r.status_code != 200:
            raise InfraError(f"Could not download repository ({r.status_code})")
        for chunk in r.iter_bytes():
            buf.write(chunk)
            if buf.tell() > MAX_REPO_BYTES:
                raise InfraError("Repository is larger than 60 MB")
    buf.seek(0)
    with tarfile.open(fileobj=buf, mode="r:gz") as tf:
        tf.extractall(dest, filter="data")
    root = next(p for p in dest.iterdir() if p.is_dir())
    return root


# ---------- uploaded zip ----------

def extract_zip(zip_path: Path, dest: Path) -> Path:
    """Safely unpacks a delivered zip (no path escape, no symlinks, size and count limits)."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ValueError("That file is not a valid zip archive.")
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_FILES:
            raise ValueError(f"The zip has more than {MAX_ZIP_FILES} files.")
        if sum(i.file_size for i in infos) > MAX_ZIP_UNPACKED:
            raise ValueError("The zip is too large once unpacked.")
        root = dest.resolve()
        for i in infos:
            name = i.filename.replace("\\", "/")
            if name.startswith("/") or ".." in Path(name).parts or ((i.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError("The zip contains an unsafe path.")
            target = (dest / name).resolve()
            if root not in target.parents and target != root:
                raise ValueError("The zip contains an unsafe path.")
        zf.extractall(dest)
    kids = [p for p in dest.iterdir() if not p.name.startswith("__MACOSX")]
    return kids[0] if len(kids) == 1 and kids[0].is_dir() else dest


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "0x" + h.hexdigest()


# ---------- published site ----------

def fetch_site(url: str, max_pages: int = 5) -> dict[str, str]:
    """Reads a published site: the home page plus a few same-site pages, as text the AI can quote."""
    base = safe_url(url)
    host = urlparse(base).netloc
    pages, queue, seen = {}, [base], set()
    while queue and len(pages) < max_pages:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        try:
            for _ in range(4):  # follow redirects manually so every hop is checked
                safe_url(u)
                r = httpx.get(u, follow_redirects=False, timeout=15, headers={"User-Agent": "ProofPayVerifier/1"})
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    u = urljoin(u, r.headers["location"])
                    if urlparse(u).netloc != host:
                        break
                    continue
                break
            else:
                continue
            if r.status_code != 200 or "html" not in r.headers.get("content-type", "") and not pages:
                if not pages:
                    raise ValueError(f"The site answered with status {r.status_code}")
                continue
        except httpx.HTTPError as e:
            if not pages:
                raise ValueError(f"The site could not be reached ({type(e).__name__})")
            continue
        html = r.text[:400_000]
        for m in re.finditer(r'href=["\']([^"\'#]+)["\']', html):
            nxt = urljoin(u, m.group(1))
            if urlparse(nxt).netloc == host and urlparse(nxt).scheme in ("http", "https") and not re.search(r"\.(png|jpe?g|gif|svg|css|js|pdf|zip|ico|webp)(\?|$)", nxt, re.I):
                queue.append(nxt.split("#")[0])
        text = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
        pages[urlparse(u).path or "/"] = text[:60_000]
    return pages


def collect_files(root: Path | None, globs: list[str] | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Text files the AI may read (bounded). Optional globs narrow the selection."""
    out: dict[str, str] = dict(extra or {})
    if root:
        cands = []
        for p in root.rglob("*"):
            if not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(root).parts) or p.is_symlink():
                continue
            rel = p.relative_to(root).as_posix()
            if p.suffix.lower() not in TEXT_EXT and p.name.lower() not in ("readme", "dockerfile", "makefile", "license"):
                continue
            if globs and not any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(p.name, g) for g in globs):
                continue
            cands.append((0 if "readme" in rel.lower() else 1 if rel.count("/") < 2 else 2, rel, p))
        total = 0
        for _, rel, p in sorted(cands)[:80]:
            if p.stat().st_size > 400_000:
                continue
            t = p.read_text(errors="ignore")[:40_000]
            if total + len(t) > 250_000:
                break
            out[rel] = t
            total += len(t)
    return out


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def judge_with_evidence(claim: str, files: dict[str, str]) -> tuple[bool, str]:
    """AI says whether the claim holds; we only believe it if the quoted proof really exists in the submitted files."""
    if not files:
        return False, "Nothing readable was submitted to check this against."
    try:
        v = compiler.judge_requirement(claim, files)
    except ai.AIError as e:
        raise InfraError(str(e))
    if not v["met"]:
        return False, v["reason"] or "The AI could not find proof of this in the delivery."
    q = _norm(v["quote"])
    if len(q) < 8:
        return False, "The AI did not cite any proof, so this is not accepted."
    if INJECTION.search(q):
        return False, "The cited text looks like an instruction aimed at the checker, so it is not accepted."
    pool = [files[v["file"]]] if v["file"] in files else list(files.values())
    if not any(q in _norm(t) for t in pool):
        return False, "The AI's cited proof was not found in the files, so it is not accepted."
    if v["confidence"] < 0.6:
        return False, "The AI was not confident enough that this is met."
    return True, f'Found in {v["file"] or "the delivery"}: "{q[:160]}"'


# ---------- individual tests ----------

def _inside(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    if root.resolve() not in p.parents and p != root.resolve():
        raise ValueError("path escapes repository")
    return p


def run_test(kind: str, spec: dict, root: Path | None, deploy_url: str | None, site: dict | None = None) -> tuple[bool, str]:
    if kind in ("file_exists", "file_contains", "command") and root is None:
        return False, "No files were submitted (upload a zip or a GitHub link) for this check."
    if kind == "ai_review":
        return judge_with_evidence(spec["claim"], collect_files(root, spec.get("paths") or None, site))
    if kind == "file_exists":
        p = _inside(root, spec["path"])
        return p.is_file(), "found" if p.is_file() else f"{spec['path']} not found"
    if kind == "file_contains":
        p = _inside(root, spec["path"])
        if not p.is_file() or p.stat().st_size > 1_000_000:
            return False, f"{spec['path']} missing or larger than 1 MB"
        ok = re.search(spec["pattern"], p.read_text(errors="ignore")) is not None
        return ok, "pattern found" if ok else f"pattern not found in {spec['path']}"
    if kind == "http":
        if not deploy_url:
            return False, "No deployed URL was submitted"
        try:
            base = safe_url(deploy_url)
            r = httpx.request(spec["method"], base + spec["path"], json=spec.get("json_body"),
                              follow_redirects=False, timeout=15)
        except (ValueError, httpx.HTTPError) as e:
            return False, f"request failed: {e}"
        if r.status_code != spec["expect_status"]:
            return False, f"expected status {spec['expect_status']}, got {r.status_code}"
        if spec.get("expect_contains") and spec["expect_contains"] not in r.text:
            return False, "response is missing the expected content"
        return True, f"status {r.status_code}"
    if kind == "command":
        return _run_in_sandbox(spec, root)
    raise ValueError(kind)


def _run_in_sandbox(spec: dict, root: Path) -> tuple[bool, str]:
    if not shutil.which("docker"):
        raise InfraError("Sandbox unavailable (docker not installed on the verifier host)")
    name = f"pp-{uuid.uuid4().hex[:12]}"
    cmd = ["docker", "run", "--rm", "--name", name, "--cpus", "1", "--memory", "1g", "--pids-limit", "512",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--network", "bridge" if spec.get("setup") else "none",  # network only when dependencies must be installed
           "-v", f"{root}:/work", "-w", "/work"]
    if settings.sandbox_runtime:
        cmd += ["--runtime", settings.sandbox_runtime]
    script = f"{spec['setup']} && {spec['cmd']}" if spec.get("setup") else spec["cmd"]
    cmd += [spec["image"], "sh", "-c", script]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=spec["timeout"])
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        return False, f"timed out after {spec['timeout']}s"
    out = (r.stdout + r.stderr)[-3000:]
    if r.returncode == 125:  # docker itself failed (bad image, daemon down)
        raise InfraError(f"Sandbox error: {out[-300:]}")
    return r.returncode == 0, out


# ---------- orchestration ----------

def run_milestone(reqs: list[dict], repo_url: str | None, ref: str | None, deploy_url: str | None, meta: dict, zip_path: Path | None = None) -> dict:
    """Returns the evidence report. Raises InfraError if our infrastructure (not the work) failed.
    Manual requirements are not machine-checked (the buyer confirms those)."""
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tmp = Path(tempfile.mkdtemp(prefix="pp-"))
    results, site, root, sha, source = [], None, None, None, "site"
    auto = [r for r in reqs if r["kind"] != "manual"]
    try:
        if zip_path:
            source, sha = "zip", sha256_file(zip_path)
            try:
                root = extract_zip(zip_path, tmp)
            except ValueError as e:
                raise InfraError(str(e))
        elif repo_url:
            source, sha = "github", resolve_commit(repo_url, ref)
            root = download(repo_url, sha, tmp)
        for r in auto:
            t0 = time.time()
            if r["kind"] == "ai_review" and deploy_url and site is None:
                try:
                    site = fetch_site(deploy_url)
                except ValueError as e:
                    site = {}
                    site_err = str(e)
            ok, detail = run_test(r["kind"], r["spec"], root, deploy_url, site)
            if r["kind"] == "ai_review" and not ok and deploy_url and site == {} and not root:
                detail = f"The published site could not be read: {site_err}"
            results.append({
                "requirement_id": r["id"], "title": "Hidden test" if r["hidden"] else r["title"], "hidden": r["hidden"],
                "kind": "hidden" if r["hidden"] else r["kind"], "passed": ok,
                "detail": "" if r["hidden"] else detail[-1500:], "ms": int((time.time() - t0) * 1000),
            })
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    n_ok = sum(x["passed"] for x in results)
    return {
        "v": 2, **meta, "source": source, "repo": repo_url, "commit_sha": sha, "deploy_url": deploy_url, "started_at": started,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": results,
        "summary": {"passed": n_ok, "total": len(results)}, "passed": bool(results) and n_ok == len(results),
    }
