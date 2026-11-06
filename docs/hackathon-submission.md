# Hermes Agent Plugin Hackathon — submission draft

**Form:** https://form.typeform.com/to/FwJLvOln
**Deadline:** 2026-11-11 22:00 UTC
**Rules:** PR to the Hermes plugin catalog + demo video on X tagging
`@NousResearch` + both links in the form.

## Fields

**Plugin Title**

```
SpendWarden
```

**Plugin Description**

```
SpendWarden is a deterministic spend policy firewall and local ledger for Hermes
agents that can move money. A pre_tool_call hook checks every payment-shaped
tool call against daily, monthly and per-call USD caps, recipient/asset/network
allowlists and an approval threshold. In enforce mode it blocks hard violations
and escalates uncertain ones to Hermes's own approval gate. Four tools add
spend_check, idempotent spend_record receipts, spend_report totals, and
x402_inspect, which decodes PAYMENT-REQUIRED and X-PAYMENT payloads without
signing. State is a local SQLite ledger under the plugin data directory. No
network calls, no credentials, no private keys, no transaction signing.
Observe mode logs only; enforce mode is opt-in.
```

**Email Address**

```
opencode.agent177c@onionmail.org
```

**Discord Username**

```
<TODO: real Discord handle>
```

**X Demo Post Link**

```
https://x.com/i_am_ahero/status/2118732352620794118
```

**GitHub Link to your Hermes Plugin Pull Request**

```
<TODO: PR URL>
```

## Before submitting

- [ ] GitHub repo is public and contains the pinned SHA.
- [ ] Catalog PR is open and CI is green.
- [ ] X demo video is under 90 seconds and tags `@NousResearch`.
- [ ] Form fields are filled; Discord handle is real.
- [ ] Keep the X post live through judging.

## Demo assets

- Video: `demo/demo.mp4` (48 s)
- Page: https://agent-payments-audit.surge.sh/spendwarden/
- Archive: https://agent-payments-audit.surge.sh/spendwarden/spendwarden-0.1.0.zip
- Banner: `docs/banner.png`
- Ledger screenshot: `docs/demo.png`
