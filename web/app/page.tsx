import Link from "next/link";

const steps = [
  ["Register and share your ID", "Both people create an account. Each gets a username. The worker gives theirs to the buyer."],
  ["Describe it and pay", "The buyer writes or speaks what they want, in English, Hindi or Hinglish. AI explains it back and builds the checks. Paying locks the money on the blockchain."],
  ["Deliver and get checked", "The worker uploads a zip, shares a GitHub link or publishes a website. AI and automatic tests check it against what was asked. For physical products the buyer presses “I received it”."],
  ["Get paid", "After a short review window the money is released automatically. Changed your mind early? Take it back until someone accepts. After that, both sides must agree."],
];

export default function Landing() {
  return (
    <main className="mx-auto max-w-5xl px-5 py-8">
      <header className="flex items-center justify-between">
        <span className="text-lg font-bold">ProofPay</span>
        <Link href="/login" className="btn-ghost">Sign in</Link>
      </header>
      <section className="py-20">
        <h1 className="max-w-2xl text-5xl font-bold leading-[1.08] tracking-tight">Pay only for work that is really delivered.</h1>
        <p className="mt-5 max-w-xl text-lg text-mute">
          The money is locked on the blockchain the moment you hire. It is released when the delivered website, app or product matches what you asked for. No chasing, no arguing over whether it was finished.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/register" className="btn-primary">Create account</Link>
          <Link href="/login?next=/jobs" className="btn-ghost">Find work</Link>
        </div>
      </section>
      <section>
        <h2 className="mb-4">How a contract works</h2>
        <ol className="grid gap-4 md:grid-cols-2">
          {steps.map(([t, d], i) => (
            <li key={t} className="panel flex gap-4 p-5">
              <span className="text-2xl font-bold text-brand">{i + 1}</span>
              <div><p className="font-semibold">{t}</p><p className="mt-1 text-sm text-mute">{d}</p></div>
            </li>
          ))}
        </ol>
      </section>
      <footer className="mt-16 border-t border-line pt-5 text-sm text-mute">Runs on MST Testnet. Testnet tokens have no cash value.</footer>
    </main>
  );
}
