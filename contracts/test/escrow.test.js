import { test, before } from "node:test";
import assert from "node:assert/strict";
import fs from "fs";
import ganache from "ganache";
import { ethers } from "ethers";

const { abi, bytecode } = JSON.parse(fs.readFileSync("artifacts/ProofPayEscrow.json", "utf8"));
const DAY = 86400, HOUR = 3600;
const WINDOW = 2 * DAY, GRACE = 3 * DAY;
const E = ethers.parseEther;
const ZERO = ethers.ZeroAddress;
let provider, admin, verifier, arbitrator, client, freelancer, stranger, base, n = 0;

const rpcTime = async (secs) => { await provider.send("evm_increaseTime", [secs]); await provider.send("evm_mine", []); };
const now = async () => (await provider.getBlock("latest")).timestamp;
const as = (s) => base.connect(s);
const newId = () => ethers.id("escrow-" + n++);
const bal = (a) => provider.getBalance(a.address);
const status = async (id, i) => (await base.getMilestones(id))[i].status;

// create (locks 3 MST over two milestones); worker = address or ZERO for an open job
async function create(worker = freelancer.address, { windows = [WINDOW, WINDOW], accept = true } = {}) {
  const id = newId(), t = await now();
  await (await as(client).createEscrow(id, worker, ethers.id("c"), ethers.id("h"), [E("1"), E("2")], [t + 5 * DAY, t + 10 * DAY], windows, { value: E("3") })).wait();
  if (accept) await (await as(freelancer).acceptContract(id)).wait();
  return id;
}

before(async () => {
  provider = new ethers.BrowserProvider(ganache.provider({ logging: { quiet: true }, wallet: { deterministic: true } }), undefined, { cacheTimeout: -1 });
  [admin, verifier, arbitrator, client, freelancer, stranger] = await Promise.all([0, 1, 2, 3, 4, 5].map((i) => provider.getSigner(i)));
  const f = new ethers.ContractFactory(abi, bytecode, admin);
  base = await f.deploy(admin.address, verifier.address, arbitrator.address, GRACE);
  await base.waitForDeployment();
});

test("creating locks the full amount in the contract", async () => {
  const before = await provider.getBalance(await base.getAddress());
  const id = await create(freelancer.address, { accept: false });
  assert.equal((await provider.getBalance(await base.getAddress())) - before, E("3"));
  assert.equal(await base.total(id), E("3"));
});

test("happy path: attest, wait out the milestone window, finalize pays freelancer", async () => {
  const id = await create();
  await (await as(verifier).attest(id, 0, ethers.id("ev"), true)).wait();
  await assert.rejects(as(stranger).finalize(id, 0)); // too early
  await rpcTime(WINDOW + 1);
  const before = await bal(freelancer);
  await (await as(stranger).finalize(id, 0)).wait();
  assert.equal((await bal(freelancer)) - before, E("1"));
  assert.equal(await status(id, 0), 3n);
});

test("each milestone keeps its own review window", async () => {
  const id = await create(freelancer.address, { windows: [HOUR, 7 * DAY] });
  await (await as(verifier).attest(id, 0, ethers.id("a"), true)).wait();
  await (await as(verifier).attest(id, 1, ethers.id("b"), true)).wait();
  await rpcTime(HOUR + 1);
  await (await as(stranger).finalize(id, 0)).wait();
  await assert.rejects(as(stranger).finalize(id, 1));
});

test("failed attestation keeps funds locked; re-attest can pass", async () => {
  const id = await create();
  await (await as(verifier).attest(id, 0, ethers.id("fail"), false)).wait();
  assert.equal(await status(id, 0), 0n);
  await (await as(verifier).attest(id, 0, ethers.id("pass"), true)).wait();
  assert.equal(await status(id, 0), 1n);
});

test("client dispute inside window, arbitrator splits 60/40", async () => {
  const id = await create();
  await (await as(verifier).attest(id, 1, ethers.id("ev"), true)).wait();
  await (await as(client).dispute(id, 1, ethers.id("reason"))).wait();
  await assert.rejects(as(client).resolve(id, 1, 6000));
  const [f0, c0] = [await bal(freelancer), await bal(client)];
  await (await as(arbitrator).resolve(id, 1, 6000)).wait();
  assert.equal((await bal(freelancer)) - f0, E("1.2"));
  assert.equal((await bal(client)) - c0, E("0.8"));
});

test("dispute rejected after window closes", async () => {
  const id = await create();
  await (await as(verifier).attest(id, 0, ethers.id("ev"), true)).wait();
  await rpcTime(WINDOW + 1);
  await assert.rejects(as(client).dispute(id, 0, ethers.id("late")));
});

test("client can approve early ('I received it'), even without attestation", async () => {
  const id = await create();
  const before = await bal(freelancer);
  await (await as(client).approve(id, 0)).wait();
  assert.equal((await bal(freelancer)) - before, E("1"));
  await assert.rejects(as(client).approve(id, 0)); // only once
});

test("unverified milestone is refundable after deadline + grace", async () => {
  const id = await create();
  await assert.rejects(as(client).refundExpired(id, 0));
  await rpcTime(5 * DAY + GRACE + 1);
  await (await as(client).refundExpired(id, 0)).wait();
  assert.equal(await status(id, 0), 4n);
});

test("input validation: self-hire, wrong value, empty, bad window, past deadline", async () => {
  const t = await now(), h = ethers.id("h");
  const go = (w, amounts, dl, win, value) => as(client).createEscrow(newId(), w, h, h, amounts, dl, win, { value });
  await assert.rejects(go(client.address, [E("1")], [t + DAY], [WINDOW], E("1")));
  await assert.rejects(go(freelancer.address, [E("1")], [t + DAY], [WINDOW], E("0.5")));
  await assert.rejects(go(freelancer.address, [], [], [], 0n));
  await assert.rejects(go(freelancer.address, [E("1")], [t + DAY], [60], E("1")));
  await assert.rejects(go(freelancer.address, [E("1")], [t + DAY], [31 * DAY], E("1")));
  await assert.rejects(go(freelancer.address, [E("1")], [t - 5], [WINDOW], E("1")));
  await assert.rejects(go(freelancer.address, [E("1")], [t + DAY, t + DAY], [WINDOW], E("1")));
});

test("duplicate id is rejected", async () => {
  const id = await create(freelancer.address, { accept: false });
  const t = await now();
  await assert.rejects(as(client).createEscrow(id, freelancer.address, ethers.id("c"), ethers.id("h"), [E("1")], [t + DAY], [WINDOW], { value: E("1") }));
});

test("only the named worker may accept; client cannot", async () => {
  const id = await create(freelancer.address, { accept: false });
  await assert.rejects(as(stranger).acceptContract(id));
  await assert.rejects(as(client).acceptContract(id));
  await (await as(freelancer).acceptContract(id)).wait();
  await assert.rejects(as(freelancer).acceptContract(id)); // already accepted
});

test("open job: any worker can accept and then gets paid", async () => {
  const id = await create(ZERO, { accept: false });
  await assert.rejects(as(client).acceptContract(id));
  await (await as(stranger).acceptContract(id)).wait();
  assert.equal((await base.escrows(id)).freelancer, stranger.address);
  const before = await bal(stranger);
  await (await as(client).approve(id, 0)).wait();
  assert.equal((await bal(stranger)) - before, E("1"));
});

test("nothing can be attested or approved before acceptance", async () => {
  const id = await create(freelancer.address, { accept: false });
  await assert.rejects(as(verifier).attest(id, 0, ethers.id("x"), true));
  await assert.rejects(as(client).approve(id, 0));
});

test("revoke before acceptance refunds everything", async () => {
  const id = await create(ZERO, { accept: false });
  await assert.rejects(as(stranger).revoke(id));
  const before = await bal(client);
  const r = await (await as(client).revoke(id)).wait();
  const gas = r.gasUsed * r.gasPrice;
  assert.equal((await bal(client)) - before + gas, E("3"));
  assert.equal(await status(id, 0), 4n);
  await assert.rejects(as(stranger).acceptContract(id));
  await assert.rejects(as(client).revoke(id));
});

test("revoke is impossible once accepted", async () => {
  const id = await create();
  await assert.rejects(as(client).revoke(id));
});

test("cancel after acceptance: request, worker agrees, unreleased funds refunded", async () => {
  const id = await create();
  await (await as(client).approve(id, 0)).wait(); // 1 MST already released
  await assert.rejects(as(freelancer).acceptCancel(id)); // nothing requested
  await assert.rejects(as(freelancer).requestCancel(id)); // only the client asks
  await (await as(client).requestCancel(id)).wait();
  await assert.rejects(as(stranger).acceptCancel(id));
  const before = await bal(client);
  await (await as(freelancer).acceptCancel(id)).wait();
  assert.equal((await bal(client)) - before, E("2"));
  assert.equal(await status(id, 0), 3n); // released stays released
  assert.equal(await status(id, 1), 4n);
  await assert.rejects(as(verifier).attest(id, 1, ethers.id("x"), true));
});

test("client can withdraw a cancel request; worker can then no longer accept it", async () => {
  const id = await create();
  await (await as(client).requestCancel(id)).wait();
  await (await as(client).withdrawCancel(id)).wait();
  await assert.rejects(as(freelancer).acceptCancel(id));
  await assert.rejects(as(client).withdrawCancel(id));
});

test("access control: attest/resolve are role-gated, finalize before pass fails", async () => {
  const id = await create();
  await assert.rejects(as(stranger).attest(id, 0, ethers.id("x"), true));
  await assert.rejects(as(client).attest(id, 0, ethers.id("x"), true));
  await assert.rejects(as(stranger).finalize(id, 0));
  await assert.rejects(as(stranger).approve(id, 0));
  await assert.rejects(as(stranger).dispute(id, 0, ethers.id("r")));
  await assert.rejects(as(verifier).attest(id, 9, ethers.id("x"), true)); // bad index
});

test("a disputed milestone survives a cancel and is still resolvable", async () => {
  const id = await create();
  await (await as(verifier).attest(id, 0, ethers.id("ev"), true)).wait();
  await (await as(client).dispute(id, 0, ethers.id("r"))).wait();
  await (await as(client).requestCancel(id)).wait();
  const c0 = await bal(client);
  await (await as(freelancer).acceptCancel(id)).wait();
  assert.equal((await bal(client)) - c0, E("2")); // only the undisputed milestone refunded
  assert.equal(await status(id, 0), 2n);
  await (await as(arbitrator).resolve(id, 0, 10000)).wait();
  assert.equal(await status(id, 0), 3n);
});

test("pause blocks new escrows; unpause restores", async () => {
  await (await base.connect(admin).pause()).wait();
  const t = await now();
  await assert.rejects(as(client).createEscrow(newId(), freelancer.address, ethers.id("c"), ethers.id("h"), [E("1")], [t + DAY], [WINDOW], { value: E("1") }));
  await (await base.connect(admin).unpause()).wait();
  await create();
});

test("contract never holds more than unsettled milestones", async () => {
  const addr = await base.getAddress();
  const before = await provider.getBalance(addr);
  const id = await create();
  await (await as(client).approve(id, 0)).wait();
  await (await as(client).approve(id, 1)).wait();
  assert.equal(await provider.getBalance(addr), before);
});
