# Three-minute video script

**Format:** first person, English, own voice. ~420 words, about 2:50 at a calm
pace; rehearse to stay under 3:00. Record screen + voice; no slides required. Numbers are from
`experiment/results/results.json`.

**Before recording:** run `python3 -m experiment.run` so the terminal output and
`RESULTS.md` on screen are from the current commit. Open `RESULTS.md` in a
readable font, and keep a second window on `experiment/fixtures/swarm_script.json`.

---

**[0:00 — medium shot, or terminal with the repo]**

Giving an AI agent a wallet used to be a demo. Now it's a product. And the
standard safety feature is a spend policy: no single payment over two dollars,
no more than ten dollars a day, ask me above fifty cents.

That works for one agent. I wanted to know whether it works for a swarm.

**[0:25 — show the six-agent diagram / fixture]**

So I attacked SpendWarden, an open-source spend firewall I maintain. Six mock agents share one wallet. Four do honest work. Two are
compromised, and they escalate: they blend in, split payments just under the
approval threshold, race each other, and then use a renamed tool.

No real money. Every payment is mock USDC on Base.

**[0:50 — show `RESULTS.md`, probe table]**

I ran three controlled probes, so each failure is isolated.

Split: six payments of forty-nine cents. The policy asked for approval exactly
zero times. In the full run, twenty-eight split payments produced zero approval
prompts, and sixteen of them executed — seven dollars sixty, with no human
decision.

**[1:10 — highlight the race row]**

Race: six agents checked the budget when ninety cents were left. All six
passed, because none had recorded yet. The ledger ended a dollar eighty over
the cap. Check-then-act is not a reservation.

**[1:25 — show the alias action in the fixture]**

Alias: a tool called `vendor_settle`, with arguments `payee` and `sum_usd`.
The detector saw nothing payment-shaped, and a dollar fifty left without a
ledger entry. In the full run, three dollars left that way — invisible to every
later budget decision.

**[1:45 — full swarm table]**

Then the full swarm. With no guardrail, all twenty-five ninety executed,
including twenty dollars eighty-six of attack spend.

With SpendWarden, attack spend fell to eleven dollars — but honest work fell to
sixty percent, because two bad agents drained the shared budget. That's the
part I didn't expect: the attack doesn't just steal money, it starves the
agents that are behaving.

**[2:05 — show the mediated run / diagram of the mediator]**

The fix isn't a tighter number. It's a different boundary.

The agents no longer hold a payment tool. They submit intents to a mediator
that holds the only wallet capability. It reserves budget atomically, so a race
can't happen. It accumulates exposure per agent and per recipient, so splitting
hits a ceiling. And a tool the agents invent has nothing to call.

Attack spend dropped to four dollars eight. No cap overrun, no unledgered
spend, and honest work stayed at ninety-seven percent.

**[2:35 — direct to camera]**

The point for recursive self-improvement is this. A system that rewrites itself
will invent tools faster than we can name them. A deny-list of bad tool names
has a short half-life. A capability boundary doesn't.

Caps are not capabilities. Thank you.

---

## Delivery notes

- Pause after "works for a swarm" and after "starves the agents that are
  behaving" — those are the two beats judges should remember.
- Don't rush the numbers; put them on screen so the viewer can read while you
  speak.
- If time runs short, cut the full-swarm "no guardrail" figure, not the
  honest-work result.
- Do not claim real-world deployment, real funds, or an adaptive adversary.
  The experiment is a mock swarm against the real policy engine.
