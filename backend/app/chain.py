import hashlib
import json
import threading
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from eth_account import Account
from web3 import Web3

from .config import settings

ABI = json.loads((Path(__file__).parent / "abi.json").read_text()) if (Path(__file__).parent / "abi.json").exists() else []
_lock = threading.Lock()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(s: str) -> str:
    return "0x" + hashlib.sha256(s.encode()).hexdigest()


def to_wei(amount) -> int:
    return int(Web3.to_wei(Decimal(str(amount)), "ether"))


def from_wei(wei) -> Decimal:
    return Decimal(int(wei)) / Decimal(10**18)


@lru_cache
def w3() -> Web3:
    return Web3(Web3.HTTPProvider(settings.mst_rpc_url, request_kwargs={"timeout": 20}))


def escrow():
    return w3().eth.contract(address=Web3.to_checksum_address(settings.escrow_address), abi=ABI)


def verifier_address() -> str | None:
    return Account.from_key(settings.verifier_private_key).address if settings.verifier_private_key else None


def _send(fn) -> str:
    """Signs and sends a transaction with the verifier key and waits for it to be mined."""
    acct = Account.from_key(settings.verifier_private_key)
    with _lock:  # one key => serialize nonces
        tx = fn.build_transaction(
            {"from": acct.address, "nonce": w3().eth.get_transaction_count(acct.address, "pending"),
             "chainId": w3().eth.chain_id, "gasPrice": w3().eth.gas_price}
        )
        tx["gas"] = int(tx["gas"] * 1.3)  # build_transaction already estimated; add headroom
        h = w3().eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
        rc = w3().eth.wait_for_transaction_receipt(h, timeout=180)
    tx_hash = "0x" + h.hex().removeprefix("0x")
    if rc.status != 1:
        raise RuntimeError(f"transaction reverted: {tx_hash}")
    return tx_hash


def _b32(h: str) -> bytes:
    return bytes.fromhex(h[2:])


def attest(escrow_id: str, idx: int, evidence_hash: str, passed: bool) -> str:
    return _send(escrow().functions.attest(_b32(escrow_id), idx, _b32(evidence_hash), passed))


def finalize(escrow_id: str, idx: int) -> str:
    """Permissionless on-chain: anyone may release a milestone once its review window has closed."""
    return _send(escrow().functions.finalize(_b32(escrow_id), idx))


def milestone_state(escrow_id: str, idx: int) -> dict:
    amount, deadline, window, passed_at, status, evidence = escrow().functions.getMilestones(_b32(escrow_id)).call()[idx]
    return {"amount": amount, "deadline": deadline, "window": window, "passed_at": passed_at, "status": status, "evidence": "0x" + bytes(evidence).hex()}
