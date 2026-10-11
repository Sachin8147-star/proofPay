"""Help chat for users (Gemini). It explains ProofPay and helps with problems; it cannot move money or change anything."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import ai, util
from .auth import current_user
from .config import settings

router = APIRouter()

SYSTEM = f"""You are the help assistant inside ProofPay, a platform where a buyer locks money in a blockchain escrow (on the MST test network, coin {settings.symbol}) and a worker gets paid when the delivered work passes agreed checks.
Reply in the language the person writes in (English, Hindi or Hinglish). Be short, friendly and concrete (under 120 words unless they ask for more). Use steps when explaining how to do something.
How it works: 1) Both people register and get a username. 2) The buyer opens New contract, writes what they want, enters the worker's username (or leaves it empty to post an open job), sets amounts and deadlines, and pays: the money is locked immediately in the escrow contract. 3) The worker sees it under Work (or the Jobs board), can chat with the buyer, and accepts. 4) The worker delivers a zip file, a GitHub link or a published website link; AI and automatic checks verify it against what was asked. For physical products the worker marks it shipped and the buyer presses "I received it". 5) After a review window the money is released automatically, or the buyer can release it earlier, or dispute inside the window (an arbitrator decides).
Cancelling: the buyer can take the money back for free until someone accepts. After acceptance, cancelling needs the worker's agreement (the buyer sends a request; if the worker agrees the unreleased money returns).
Wallet: the Wallet page shows balance, locked money (tap the (i) to see why it is locked), unlocked money and history. Locked money cannot be spent until released or refunded.
Rules: never ask for or accept private keys, seed phrases or passwords. If someone shares one, tell them to stop and treat it as compromised. You cannot see their contracts or move funds. For account-specific problems, tell them what to check and to contact support through their contract chat or the admin. Do not give legal or financial advice. If you do not know, say so."""


class Msg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=2000)


class ChatIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=20)
    page: str | None = Field(None, max_length=120)


@router.post("/assistant/chat")
def chat(body: ChatIn, user=Depends(current_user)):
    if body.messages[-1].role != "user":
        raise HTTPException(400, "The last message must be from you")
    key = f"help:{user['id']}"
    util.rate_limit(key, 40, 3600, "Help chat limit reached for this hour. Try again later.")
    system = SYSTEM + (f"\nThe person is currently on the page: {body.page}" if body.page else "")
    try:
        reply = ai.generate_text(system, [m.model_dump() for m in body.messages], max_tokens=800)
    except ai.AIError as e:
        util.refund(key)
        raise HTTPException(503 if not ai.configured() else 502, str(e))
    return {"reply": reply}
