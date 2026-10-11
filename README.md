# ProofPay

Escrow that releases payment only when the agreed tests pass against the submitted code. Runs on **MST Testnet** (chain ID `0x5752035` = 91562037).

| Folder | What it is |
|---|---|
| `contracts/` | `ProofPayEscrow.sol` (fund-first escrow, open jobs, cancel-by-agreement, verifier attestations, per-part review windows, disputes, refunds) + compile/deploy scripts + tests |
| `supabase/migrations/` | Postgres schema: run `001_schema.sql`, `002_chat_notifications.sql`, then `003_marketplace_registration.sql`, in the Supabase SQL Editor |
| `backend/` | FastAPI: contracts, Gemini AI, zip/site/shipment verification, open jobs board, wallet summary, help chat, chain indexer, admin API |
| `web/` | Next.js app: client dashboard, freelancer dashboard, wallet, public verify and work-record pages, admin dashboard |

## How it works
1. **Register** (name, email, phone, where you heard about us, a unique username, password). The username is your ID: a worker gives it to the buyer.
2. **Buyer: New contract.** Write or speak (English, Hindi, Hinglish) what you want. Gemini explains the idea back, suggests improvements and says how each part will be checked. A contract can mix website/app parts and physical products. Enter the worker's username, or leave it empty to post an **open job**.
3. **Pay = lock.** `createEscrow` locks the whole amount on MST Testnet immediately. Until someone accepts, the buyer can **revoke** and get everything back for free.
4. **Worker: My work / Find work.** Named contracts appear under My work; open jobs appear on the Jobs board where workers can chat privately with the poster before accepting.
5. **Deliver.** A `.zip` (AI checks it contains what was asked), a GitHub link, or a published website (opened and checked). Physical product: the seller marks it shipped, the buyer presses **"I received it"**. Passing results are hashed and attested on-chain.
6. **Release.** After the per-part review window (1-30 days) payment releases automatically, or earlier when the buyer approves. The buyer can dispute only inside the window; the arbitrator resolves it from the admin dashboard.
7. **Cancel after acceptance** needs agreement: the buyer requests, the worker agrees, the unreleased money returns.
8. **Wallet page**: real balance (unlocked), money locked for your jobs and money waiting for you (tap **i** for why and when it unlocks), activity history, and all network transactions. A **Help** page has a Gemini assistant for questions.
9. `/verify/<hash>` lets anyone recompute the evidence hash. `/p/<username>` is the worker's public record.

## What makes it different
- **Plain-language start**: describe the idea by voice or text; the AI explains, suggests and shows how it will be checked.
- **AI checks that cannot be bluffed**: an AI check only counts if the quote it cites is found verbatim in the delivered files; text trying to instruct the AI is ignored.
- **Vague-requirement checker**, **practice runs** (private, never on-chain), **hidden tests committed by hash**, **chat**, **notifications**, and a **keeper** that pays out after the review window.

## Tests
```bash
cd contracts && npm test                      # 21 contract tests on a local EVM
cd backend && pytest                          # 156 tests: API, AI client, delivery, chat, notifications, and a real-chain integration run
cd web && npm test                            # 43 tests: wizard, register, wallet, jobs, help chat, delivery form, chat, helpers
```
The backend suite uses an in-memory stand-in for Supabase and a stubbed Gemini; its chain tests deploy the compiled contract to a local ganache node.

## Setup (about 20 minutes)
**0. Check the chain**
```bash
curl -s -X POST https://testnetrpc.mstblockchain.com -H "content-type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}'   # expect 0x5752035
```
**1. Supabase**: create a project, run the three files in `supabase/migrations/` in order (001, 002, 003). In Authentication > Providers > Email keep "Confirm email" on (or set `REQUIRE_VERIFIED_EMAIL=false` in `.env` for local testing). Sign up once in the app, then make yourself admin:
`update public.profiles set is_admin = true where email = 'you@example.com';`

**2. Keys**: `cp .env.example .env` and fill it. Create three NEW wallets (deployer, verifier, arbitrator). Fund deployer and verifier from the MST testnet faucet.

**3. Contract**
```bash
cd contracts && npm install
npm test            # 21 tests on a local EVM
npm run deploy      # prints the address -> set ESCROW_ADDRESS (.env) and NEXT_PUBLIC_ESCROW_ADDRESS (web/.env.local)
```
Set `INDEXER_START_BLOCK` to the deployment block (see the deploy tx on testnet.mstscan.com).

**4. Backend**
```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
pytest && uvicorn app.main:app --reload --port 8000
```
**5. Web**
```bash
cd web && cp .env.example .env.local   # fill Supabase URL/anon key + escrow address
npm install && npm run dev
```
Client/freelancer app: http://localhost:3000. Admin: http://admin.localhost:3000 (Chrome/Edge resolve `*.localhost`). In production set `NEXT_PUBLIC_ADMIN_HOST=admin.yourdomain.com`; on every other host `/admin` returns 404.

## Production notes (read before real users)
- **Sandbox**: `command` tests run in Docker on the verifier host (needs Docker; not available on Render/Vercel, use a VPS, Fly.io or Railway). Containers drop all capabilities, are resource-limited, and have **no network** except during an optional install step. For untrusted freelancers use gVisor (`SANDBOX_RUNTIME=runsc`) or Firecracker.
- **Verifier key** is a trust point: it can attest any result. The public evidence hash and the challenge window limit the damage; move to multiple verifiers later.
- **Background runs** use FastAPI background tasks; move to Redis + a worker before heavy traffic.
- **Private repos**: set `GITHUB_TOKEN`, or build a GitHub App for per-installation access.
- **Terms are immutable** once the money is locked. To change them, revoke (free until someone accepts) and create a new contract.
- Testnet MST has no cash value. Moving to a mainnet or stablecoin requires an audit of `ProofPayEscrow.sol` first.
- The explorer history uses Blockscout's `/api/v2/addresses/{addr}/transactions`; if MSTScan changes it, the wallet page falls back to a link and balances still come from the RPC.

## Upgrading from an older version
Run `003_marketplace_registration.sql`; **redeploy the contract** (constructor and ABI changed: `npm run deploy`, then update `ESCROW_ADDRESS`, `NEXT_PUBLIC_ESCROW_ADDRESS`, `INDEXER_START_BLOCK`); replace `ANTHROPIC_*` with `GEMINI_API_KEY` in the root `.env`; restart backend and web. Old contracts on the previous escrow address are not shown by the new one.
