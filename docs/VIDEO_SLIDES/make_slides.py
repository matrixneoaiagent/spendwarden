from pathlib import Path
import subprocess
BASE=Path('/home/kozak/AI/spendwarden/docs/VIDEO_SLIDES')
W,H=1280,720; BG="#0b1017"; GREEN="#7CFFB2"; BLUE="#6EC6FF"; DIM="#8FA3B8"; WHITE="#EAF2F8"; ORANGE="#FFB86B"
slides=[
("CONTAINING RUNAWAY SPEND IN AGENT SWARMS","SpendWarden  ·  AI Alignment Foundation Hackathon 2026\n\nA reproducible red-team of policy enforcement under escalation.\n\nMatrix Neo  ·  online track  ·  2026-12"),
("THE PROBLEM","Agents can escalate spend and tool use faster than a human can review.\n\nPrompt-level rules are not a boundary: split calls, races and aliased arguments can slip through.\n\nWe test whether a policy layer still holds when the swarm adapts."),
("THE EXPERIMENT","64-call frozen swarm script: 30 honest actions, 34 adversarial.\n\nThree guardrails: none, SpendWarden, mediated mitigation.\n\nThe harness imports the real policy.py / storage.py unmodified; mock USDC only.\n\nMetrics: executed spend, attack spend, containment, honest actions allowed, over-cap, unledgered."),
("RESULTS","Guardrail        Executed   Attack    Contained   Honest   Over cap   Unledgered\nNone             $25.90     $20.86    0.0%        30/30    $15.90     —\nSpendWarden      $12.96     $11.00    47.3%       18/30    $2.96      $3.00\nMediated         $8.72      $4.08     80.4%       29/30    $0.00      $0.00\n\nSame 64-call script; results/ is generated, not hand-written."),
("THREE FAILURE MODES","SPLIT   28 × $0.45–0.49, zero approval prompts; 16 executed ($7.60).\n\nRACE    six parallel calls against $0.90 remaining all passed; ledger $11.80 vs $10 (+$1.80).\n\nALIAS   vendor_settle with payee / sum_usd undetected; $1.50 probe, $3.00 in the full run unledgered."),
("THE MITIGATION","Capability boundary (no generic vendor_settle).\n\nAtomic reservation for concurrent calls.\n\nPer-agent and per-recipient exposure.\n\nFail-closed parsing of tool arguments.\n\nCloses all three probes. Cost: 1/30 honest false positive. Residual attack spend is the explicit $2/agent/recipient allowance."),
("WHY IT MATTERS FOR RSI","Self-improving systems will route around rules that are only text.\n\nThe boundary must be enforced where the money moves, and the test must be reproducible.\n\nLimitations: mock USDC, frozen script, one policy.\nNext: adaptive attacker, real x402, multi-day horizon."),
("REPRODUCE","github.com/matrixneoaiagent/spendwarden\n\ndocs/PAPER.pdf   (2 pages)\nexperiment/      (18 tests, frozen 64-call fixture)\ndocs/VIDEO_SCRIPT.md\n\nMatrix Neo  ·  AIAF Brazil 2026  ·  online"),
]
def run(cmd):
    r=subprocess.run(cmd,capture_output=True,text=True)
    if r.returncode: print("ERR",r.stderr[-400:])
for i,(title,body) in enumerate(slides,1):
    t=BASE/f"t{i}.txt"; b=BASE/f"b{i}.txt"; t.write_text(title); b.write_text(body)
    out=BASE/f"slide{i}.png"
    run(["convert","-size",f"{W}x{H}","xc:"+BG,
      "(","-background",BG,"-fill",GREEN,"-font","DejaVu-Sans-Bold","-pointsize","38","-size","1160x90",f"caption:@{t}",")","-geometry","+60+40","-composite",
      "(","-background",BG,"-fill",WHITE,"-font","DejaVu-Sans-Mono","-pointsize","21","-size","1160x540",f"caption:@{b}",")","-geometry","+60+150","-composite",
      "-fill",DIM,"-font","DejaVu-Sans-Mono","-pointsize","15","-annotate","+60+690","SpendWarden · AIAF Brazil 2026 · 2026-11-25",str(out)])
print("done")
