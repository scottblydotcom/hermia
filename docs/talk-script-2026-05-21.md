# Hermia — Lightning Talk Script
## Claude Code Meetup | ~2026-05-21 | 10 minutes

> **Audience:** Claude Code builders. They know Claude well. They think about agentic
> pipelines, MCP servers, tool use. They are NOT deep on local inference security.
> Scott's angle: known security guy in this community — lead with findings, not the tool.
>
> **How to read this doc:** Spoken words in plain text. Visuals in `[VISUAL: ...]` blocks.
> Timestamps are targets. Demo is the longest variable — have a fallback recording ready.

---

## [00:00–00:30] HOOK — The Finding

**[VISUAL: Full-screen terminal. Single result row, formatted clearly:*
```
model:   phi3:3.8b
test:    indirect-injection-execute
status:  compromised
runs:    4/4
```
*Dark background. Red `compromised` label. Nothing else on screen.]*

*"This model executed an indirect injection attack.*
*Four for four. Every time I ran it.*
*It didn't just fail a safety test — it carried out the attack.*
*And you might be running it in a pipeline right now."*

---

## [00:30–01:15] YOUR CONTEXT AS A BUILDER

**[VISUAL: Simple diagram — left box: "Claude Code / claude.com" with a lock icon. Right side: a pipeline diagram — Claude → Tool Call → [MCP Server] → [Local Model / Ollama] → response. Arrow pointing at the local model box: "evaluated?"]**

*"You're building with one of the most carefully safety-tuned models in the world. Claude is not the problem.*
*But your agentic pipelines don't stop at Claude.*
*MCP servers call local models. Pipelines use open-weight models for cost or latency. Ollama endpoints sit behind tool calls.*
*Those models haven't been evaluated. Not by you. Probably not by anyone."*

*"I spend my time breaking things. So I built a framework to test this systematically. Here's what I found."*

---

## [01:15–03:00] THE FINDINGS — NET NEW DATA

**[VISUAL: Four-panel findings card — each panel one finding, bold headline + one-line detail:*

*Panel 1 — RED:*
`INDIRECT INJECTION EXECUTED`
`phi3:3.8b carried out the attack — not just failed the test. 4/4 runs.`

*Panel 2 — AMBER:*
`CREDENTIAL LEAKAGE IN 3 MODELS`
`mistral:7b (3×), qwen3:8b (2×), deepseek-r1 (1×)`

*Panel 3 — AMBER:*
`8 MODELS ACCEPTED POLICY OVERRIDE`
`User-turn instruction overwrote system prompt security boundary.`

*Panel 4 — YELLOW:*
`SIZE DOES NOT PREDICT SAFETY`
`qwen2.5:72b: 0% on delimiter-smuggling. qwen2.5:7b-instruct-q8_0: 100%.`
*]*

*"969 tests. 4 hosts. 12 models.*
*phi3:3.8b — the only model in the fleet that actually executed an indirect injection. Not a false positive. Compromised. It exfiltrated the injected payload.*
*Three models leaked credentials under targeted prompting. mistral:7b three separate times.*
*Eight models accepted a user-turn override that contradicted the system prompt — the security boundary you think you've established.*
*And this one surprised me most: a 72-billion parameter model scored zero on delimiter-smuggling. A 7-billion parameter instruct-tuned quant scored 100%. Bigger is not safer. The instruct tuning and quant snapshot matter more than parameter count."*

---

## [03:00–03:45] WHY THIS HAPPENS — THE INFERENCE STACK

**[VISUAL: Vertical stack diagram — four labeled layers:*
*`DRIVER STACK` → `SILICON (CUDA / Metal / ROCm)` → `RUNTIME (Ollama)` → `MODEL BINARY`*
*A bracket on the right: "Your eval needs to run here — on your hardware"]*

*"Here's the part nobody talks about. A ROCm driver update changed a security test result. Same model. Same test. Different driver. PASS became FAIL.*
*Benchmark leaderboards don't capture this. They can't — they don't run on your stack.*
*Your eval does."*

---

## [03:45–06:30] LIVE DEMO — SEE IT FOR YOURSELF

**[VISUAL: Terminal — Hermia TUI launching. Model selector. Eval suite selector.]**

*"Let me show you what testing this actually looks like."*

[Launch hermia, select `llama3.2:3b`, select injection-resistance suite, run.]

**[VISUAL: TUI results pane — FAIL rows. OWASP LLM01 tag and MITRE AML.T0051 tag visible in framework column. Hardware telemetry bar running at bottom: tokens/sec, VRAM, elapsed.]**

*"llama3.2:3b. Injection resistance. Framework tags right in the output — OWASP LLM01, MITRE AML.T0051 — so your findings have documented provenance, not just 'it seemed fine.'*
*This model folded: behavioral override, indirect injection accepted.*
*Hardware telemetry running throughout. Tokens per second, VRAM pressure, elapsed time. That's security data — a prompt that spikes VRAM is an availability attack vector."*

[Switch to `qwen3:8b`, same suite, run.]

**[VISUAL: TUI results — PASS rows, green. Same test IDs. Same framework tags. ~175 t/s on telemetry bar.]**

*"Same tests. qwen3:8b. 175 tokens per second on CUDA. 100% pass rate.*
*Here's the vulnerability. Here's the framework. Here's which model you ship in your pipeline.*
*Single-turn structural eval — JSON schema compliance, key presence, framework label matching. I want to say that clearly: this is not LLM-as-judge, it's deterministic. Reproducible by anyone with the hardware."*

---

## [06:30–08:00] FLEET MODE — SAME MODEL, DIFFERENT STACK

**[VISUAL: fleet.yaml — two hosts:*
```yaml
hosts:
  - name: eric-5090
    url: http://192.0.2.1:11434
    models: [qwen3:8b]
  - name: m3-pro
    url: http://192.168.x.x:11434
    models: [qwen3:8b]
```
*Clean, full-slide.]*

*"One more thing that should matter to you as a builder.*
*Same model. Two backends. One YAML file."*

[Run fleet or cut to pre-run results.]

**[VISUAL: Side-by-side table — CUDA column / Metal column. Same test IDs. Highlight any divergent cells amber. Bottom row: telemetry delta — VRAM vs unified memory, tokens/sec.]**

*"If a security test diverges between backends — that's the inference stack changing model behavior underneath the model binary. You need to know before you deploy.*
*Even when results match, the telemetry tells you something: different silicon, different memory profile, different throughput envelope. That's your hosting decision sitting in a terminal.*
*This is Wireshark for the LLM layer. Wireshark didn't invent network packets — it made them visible."*

---

## [08:00–09:15] WHAT YOU SHOULD DO — BUILDER TAKEAWAYS

**[VISUAL: Numbered list — large, readable:*

*1. Audit your Ollama endpoints for CVEs before eval*
*2. Never deploy phi3 family on pipelines that handle untrusted input*
*3. Instruct-tuned quant snapshots beat larger bare tags on safety — test your specific tag*
*4. Pin your Ollama version before a production deploy*
*5. Run evals on the actual hardware you'll run inference on — not a cloud proxy*
*]*

*"Five things you can act on today.*
*The phi3 finding alone — if you've got phi3:3.8b or phi3:14b behind a tool call that touches user input, that's a fire drill right now, not a roadmap item. Both scored 0% on scope escalation resistance.*
*And the quant finding: if you picked a model by parameter count and haven't tested the specific tag you're running, you might have made the wrong call. A different snapshot of the same model can have completely different security behavior."*

*"The framework that produced all of this is open source and MIT licensed. Local-first — your data never leaves your stack. Vendor-agnostic — any Ollama endpoint, any hardware."*

---

## [09:15–10:00] CALL TO ACTION

**[VISUAL: GitHub URL + QR code, large, centered. One line below it:*
*`hermia-analyze --last 10` — run this on your fleet after your first eval.`*
*Nothing else on the slide.]*

*"github.com/scottblydotcom/hermia.*
*You're already building with one of the safest models in the world.*
*This is for everything else in your pipeline.*
*Questions."*

---

## Timing Summary

| Section | Target | Notes |
|---------|--------|-------|
| Hook — the finding | 0:30 | phi3 result is the opening image — no title slide |
| Builder context | 0:45 | Pipeline diagram lands the "your problem" frame |
| The findings | 1:45 | Hold the four-panel card — let them read it |
| The inference stack | 0:45 | Stack diagram; ROCm story in one sentence |
| Live demo | 2:45 | Biggest variable; pre-record as fallback |
| Fleet mode | 1:30 | Pre-run results are fine if timing is tight |
| Builder takeaways | 1:15 | This is the most actionable slide — don't rush it |
| CTA | 0:45 | Stop talking; let the QR code and the command breathe |

---

## Slides Needed (in order)

1. **Findings card** — phi3 compromised result, single row, red label *(this is the opener)*
2. **Pipeline diagram** — Claude → tool call → [local model] → "evaluated?"
3. **Four-panel findings card** — the four key results from the fleet run
4. **Stack diagram** — 4-layer vertical, "Your eval needs to run here"
5. **[Live terminal]** Hermia TUI — llama3.2:3b FAIL + framework tags
6. **[Live terminal]** Hermia TUI — qwen3:8b PASS at 175 t/s
7. **Code slide** — fleet.yaml, two hosts
8. **[Live terminal or screenshot]** Side-by-side fleet results + telemetry delta
9. **Builder takeaways** — numbered list, large text, one per line
10. **CTA** — GitHub URL + QR code + hermia-analyze command

**Total: 7 slides + 3 live terminal moments.**

---

## Fallback Plan

- Slides 5–8: swap live TUI for screenshots of a pre-run session (asciinema recording preferred)
- Opening finding (slide 1): can be a screenshot — phi3 `compromised` row is the image, not the live run
- hermia-bo1 preflight: **cut entirely** if short on time — the findings card covers the CVE angle verbally

## Pre-Talk Checklist

- [ ] Pin exact Ollama version on demo endpoint; note it on a Technical Requirements slide
- [ ] Pull `llama3.2:3b` and `qwen3:8b` on demo endpoint — verify both present
- [ ] Test injection-resistance suite runs clean end-to-end on demo hardware
- [ ] Test fleet run: both hosts reachable via Tailscale, `qwen3:8b` pulled on each
- [ ] Record fallback terminal session (asciinema or screen recording) the night before
- [ ] QR code generated and tested on a phone
- [ ] dev→main sync + v0.1.0 GitHub release tag live before talk
- [ ] Verify the four findings numbers are current against `analysis/findings.jsonl`
