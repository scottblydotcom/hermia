# LLM Benchmark Landscape 2026: Comprehensive Briefing for Hermia Opus Review

**Prepared:** 2026-05-10  
**Purpose:** Full competitive landscape briefing covering performance, safety, agentic, and security evaluation tools — to frame Hermia's position and differentiation ahead of the Claude Opus review session.

---

## 1. Executive Summary

The LLM evaluation landscape in May 2026 is defined by a single structural contradiction: benchmarks are being saturated faster than they can be replaced. The original performance canon — MMLU, HumanEval, GSM8K — has been effectively retired for frontier model comparison. MMLU now has top models clustered above 88%, HumanEval is at 97%+, and GSM8K is at 99%. The replacement tier (MMLU-Pro, GPQA-Diamond, MATH-500) is itself approaching saturation, with GPQA-Diamond frontier scores now above 94%. Only Humanity's Last Exam (HLE), ARC-AGI-2, and LiveBench continue to show genuine separation between top models as of May 2026. Stanford HELM enters maintenance mode June 1, 2026. The HuggingFace Open LLM Leaderboard is retiring, explicitly citing benchmark obsolescence. The field has fragmented: there is no single canonical leaderboard.

The safety and alignment benchmark landscape is similarly fractured. TruthfulQA, BBQ, and RealToxicityPrompts remain widely cited but are not rigorously maintained or updated. The more operationally meaningful safety tools — HarmBench, Garak, PyRIT, Promptfoo — are active but sit in a different category: they are red-teaming frameworks, not passive benchmarks. StrongREJECT (Dec 2024), XSTest, and HELM Safety represent a newer generation of more nuanced safety measurement, but no single benchmark has achieved the canonical status that MMLU held for capability. A major April 2026 UC Berkeley study showed that all eight major agentic benchmarks (SWE-bench, WebArena, OSWorld, GAIA, and others) can be reward-hacked by automated scanning agents without solving a single real task — a fundamental validity crisis for the agentic evaluation space.

Against this backdrop, Hermia occupies a genuinely differentiated position. It is not a passive benchmark or a pure research tool. It is an interactive, local-first evaluation harness with live system telemetry, MITRE-tagged security tests, agentic scoring, and direct Ollama integration (v0.1); fleet-wide operation via LiteLLM ships in v0.2. Nothing in the current market combines all of these properties. The gap Hermia fills — operational security evaluation of local AI fleets with hardware-awareness — is not addressed by any existing tool. The primary competitive risk is not duplication but irrelevance: the field is moving toward LLM-as-judge automated evaluation, and Hermia's interactive TUI model will need a coherent strategy for integrating that paradigm without losing its operational identity.

---

## 2. Performance / Capability Benchmarks

### 2.1 Summary Table

| Benchmark | Domain | Status (May 2026) | Frontier Score | Saturation? | Maintained By |
|---|---|---|---|---|---|
| MMLU | General knowledge, 57 subjects | Saturated | ~88–90% | Yes — retired for frontier use | Academic (Hendrycks et al.) |
| MMLU-Pro | Harder 10-choice MMLU variant | Near-saturated | ~89.8% (Gemini 3 Pro) | Approaching | CMU/community |
| HumanEval | Code generation, 164 problems | Fully saturated | 97.6% (Claude Sonnet 4.5) | Yes | OpenAI (unmaintained) |
| HumanEval+ | HumanEval with 80× more tests | Near-saturated | 95.1% (o3-mini high) | Near | EvalPlus team |
| LiveCodeBench | Contamination-resistant competitive coding | Active | 93.5% (DeepSeek-V4-Pro-Max) | No | LiveCodeBench team |
| HELM | Holistic multi-task evaluation | Entering maintenance | Varies | Mixed | Stanford CRFM |
| BIG-Bench Hard | 23 hard multi-step reasoning tasks | Active but approaching saturation | 88.9% (Qwen3 235B) | Approaching | Google Brain |
| BIG-Bench Extra Hard (BBEH) | Harder successors to BBH tasks | Active | 9.8–44.8% (best models) | No | Google |
| MT-Bench | Multi-turn conversational quality | Superseded by Arena | N/A | Yes | LMSYS/Berkeley |
| GSM8K | Grade-school math, 8.5K problems | Fully saturated | 99% (GPT-5.3 Codex) | Yes | OpenAI (unmaintained) |
| MATH-500 | Competition math, 500 problems | Near-saturated at top | ~97%+ frontier | Approaching | Hendrycks et al. |
| AIME 2025 | AMC/AIME competition math | Saturated at frontier | 100% (Grok-4 Heavy, GPT-5.2 Pro) | Yes | Competition-sourced |
| GPQA-Diamond | PhD-level biology/chemistry/physics | Active, approaching saturation | 94.3% (Gemini 3.1 Pro) | Approaching | NYU / Scale AI |
| SWE-Bench Verified | Real GitHub issue resolution (agentic) | Active, gold standard | 93.9% (Claude Mythos Preview) | No (hard) | Princeton / SWE-bench team |
| LiveBench | Monthly-refreshed multi-domain | Active | Top models <70% | No | LiveBench team |
| Humanity's Last Exam (HLE) | 2,500 expert-academic questions | Active, frontier separator | 44.7% (Gemini 3.1 Pro Preview) | No | CAIS + Scale AI |
| ARC-AGI-2 | Abstract visual reasoning, fluid intelligence | Active | 85% (GPT-5.5) | No | ARC Prize / François Chollet |

### 2.2 Narrative

**MMLU / MMLU-Pro.** MMLU (Massive Multitask Language Understanding, 2020) was the defining benchmark of the 2022–2024 era — 57 academic subjects, 14K questions, multiple-choice. It is now fully retired for frontier use: the top models all cluster above 88%. MMLU-Pro extended the format to 10 choices and harder reasoning-focused questions; as of May 2026 Gemini 3 Pro sits at 89.8%, and the benchmark is widely described as "approaching saturation." A multilingual extension, MMLU-ProX, was published at EMNLP 2025 covering 29 languages, providing some remaining utility for international and low-resource language comparisons. For Hermia's purposes, MMLU scores are useful only as a baseline sanity check for small local models (7B–13B), where there is still meaningful variance between 60–90%.

**HumanEval / HumanEval+ / LiveCodeBench.** OpenAI's HumanEval (164 hand-crafted Python functions) was the canonical coding benchmark from 2021–2024. Claude Sonnet 4.5 now scores 97.6%; the benchmark has no discriminative value for frontier models. HumanEval+ (EvalPlus framework, 764 test cases per problem rather than the original 7–8) is modestly more demanding but also near-saturated at ~95%. LiveCodeBench — continuously sourcing fresh problems from LeetCode, AtCoder, and CodeForces — is now the most contamination-resistant coding signal and shows meaningful separation: DeepSeek-V4-Pro-Max leads at 93.5%, with a visible gap between model tiers. For local-fleet eval purposes (Hermia's context), HumanEval remains useful for fast sanity-checking code completion capability of models like Qwen, Llama, and Mistral variants.

**HELM (Stanford).** HELM (Holistic Evaluation of Language Models, 2022) was the most ambitious comprehensive evaluation framework: 42 scenarios, 7 metrics per scenario, open reproducible methodology. HELM Lite and domain extensions (MedHELM, HELM Safety, HELM Long Context) continued into 2025. As of May 2026, HELM core is entering maintenance mode on June 1, 2026 — the Stanford CRFM team has explicitly stated that "as model capabilities change, benchmarks need to follow." HELM's open Python framework and structured methodology remain valuable, and IBM has built an enterprise extension (finance, legal, climate, cybersecurity domains). HELM's philosophy — holistic, multi-metric, reproducible — directly informs Hermia's design.

**BIG-Bench Hard / BIG-Bench Extra Hard.** BIG-Bench (2022, Google) was a 204-task crowdsourced benchmark covering diverse capabilities. BIG-Bench Hard (BBH) isolated the 23 tasks where LLMs underperformed humans at launch; these require multi-step reasoning, temporal understanding, spatial reasoning, and deductive logic. BBH is approaching saturation — SOTA at 88.9% (Qwen3 235B) as of May 2026. In response, Google released BIG-Bench Extra Hard (BBEH) in early 2026, redesigning each task to be harder; best models score only 9.8–44.8%, making it a genuine frontier separator. BIG-Bench proper is no longer maintained; BBH remains actively cited.

**MT-Bench.** MT-Bench (LMSYS, 2023) evaluated multi-turn instruction following via GPT-4 as judge, across 80 challenging questions in 8 categories. It was foundational in establishing the LLM-as-judge evaluation paradigm. MT-Bench scores are no longer actively maintained; Chatbot Arena has superseded it as the go-to human-preference signal. MT-Bench's methodology (GPT-4-as-judge for conversational quality) is still widely adopted in derivative systems.

**GSM8K / MATH / AIME.** GSM8K (8,500 grade-school math problems, OpenAI 2021) is fully retired for frontier use at 99%. MATH-500 (500 competition-level problems) remains useful at the frontier but is approaching saturation. AIME 2025 scores are 100% for multiple frontier models. The math reasoning battle has moved to harder unpublished competition problems, HMMT, and olympiad-level tasks that have not yet been formalized as benchmarks. GSM8K remains valuable for comparing smaller models in the 7B–70B range.

**GPQA-Diamond.** The Graduate-Level Google-Proof Q&A benchmark (198 questions, biology/chemistry/physics, PhD-verified) was the hardest knowledge benchmark for most of 2024–2025. As of May 2026, frontier models score 91–94%; the PhD expert baseline is 65–70%. GPQA-Diamond is approaching saturation but remains a useful discriminator at the frontier. It is part of the standard Artificial Analysis intelligence methodology.

**SWE-Bench Verified.** SWE-Bench tasks models with resolving real GitHub issues on real codebases. The Verified variant (500 hand-validated issues) is the gold standard for agentic coding evaluation. As of May 2026, Claude Mythos Preview leads at 93.9%; the benchmark retains meaningful separation because it requires genuine multi-file code understanding, not just pattern matching. SWE-rebench and SWE-bench-Live (post-2025 issues to prevent training contamination) are active extensions. SWE-bench is covered in more depth in the Agentic section.

**LiveBench.** LiveBench (2024, ongoing) is the most contamination-resistant general benchmark: new questions are released monthly, sourced from recent arXiv papers, news articles, and other fresh content. 18 tasks across math, coding, reasoning, language, instruction following, and data analysis. Top models score below 70%, making it one of the few benchmarks that still differentiates across the full frontier tier. LiveBench is actively maintained and updated as of May 2026.

**Humanity's Last Exam (HLE).** Released January 2025 by the Center for AI Safety and Scale AI, published in Nature (2026). 2,500 questions by subject-matter experts across 100+ disciplines — designed explicitly to be the final closed-ended benchmark that frontier models cannot saturate. As of May 2026, the top score is 44.7% (Gemini 3.1 Pro Preview); the benchmark remains a genuine frontier separator. HLE is the current gold standard for "is this model genuinely expert-level?"

**ARC-AGI-2.** François Chollet's Abstract Reasoning Corpus, second generation (2025). Visual grid transformation tasks requiring fluid intelligence — the benchmark is explicitly designed to test generalization, not memorization. Average human performance is 66%; as of May 2026, GPT-5.5 leads at 85%. Notably, the lab winning on coding benchmarks (coding-focused models) is not the lab winning on ARC-AGI-2 (reasoning-focused models) — these capabilities do not transfer. ARC-AGI-3, planned for 2026, will add interactive adaptive environments.

---

## 3. Safety / Alignment Benchmarks

### 3.1 Summary Table

| Benchmark | Focus Area | Status (May 2026) | Key Metric | Maintained? |
|---|---|---|---|---|
| TruthfulQA | Factual accuracy / hallucination avoidance | Widely cited, static dataset | % truthful responses (817 questions) | Limited — original dataset static |
| BBQ | Bias in ambiguous QA (social groups) | Actively used in research | Accuracy under ambiguity | Academic (Parrish et al.) |
| WinoBias | Gender bias in coreference resolution | Historical reference, largely superseded | Debiasing method evaluation | Minimal maintenance |
| RealToxicityPrompts | Open-ended toxicity generation from natural prompts | Widely cited, static | Toxicity rate via Perspective API | AllenAI — static |
| BOLD | Bias in open-ended language generation (23K prompts) | Active | Toxicity, sentiment, gender polarity | Amazon Science |
| SafetyBench | Safety multiple-choice (Chinese/English) | Active | Multiple-choice accuracy | Tsinghua / academic |
| SimpleSafetyTests (SST) | Critical safety risks: self-harm, CSAM, violence | Active | Binary refusal rate (100 questions) | Vidgen et al. |
| XSTest | Over-refusal / false refusal calibration | Active | Refusal rate on safe vs. unsafe prompts | Academic |
| StrongREJECT | Jailbreak emptiness / hollow refusals | Active (Dec 2024) | Harm scoring on 313 behaviors | Academic |
| HELM Safety | Integrated safety within HELM framework | Entering maintenance with HELM | Multiple safety metrics | Stanford CRFM |
| TamperBench | Safety under fine-tuning and tampering | New (Feb 2026) | Post-fine-tune refusal retention | Academic |
| SafeRBench | Safety in reasoning models (chain-of-thought) | New (Nov 2025) | Safety across reasoning traces | Academic |

### 3.2 Narrative

**TruthfulQA.** Developed by Lin et al. (2021), TruthfulQA tests 817 questions across 38 categories (health, law, finance, politics) where humans commonly hold misconceptions. Models are scored on truthfulness and informativeness; a model that refuses all questions scores 100% on truthfulness but 0% on informativeness — the combined metric matters. TruthfulQA remains widely cited in model cards and papers but has not been updated since release. Frontier models now score very high; the benchmark is more useful for identifying specific failure modes in smaller models or fine-tuned variants than for discriminating between frontier systems.

**BBQ (Bias Benchmark for QA).** Parrish et al. 2022. 58,492 questions covering nine social dimensions (age, disability, gender, nationality, race, religion, SES, sexuality, appearance) with explicit ambiguous and disambiguated contexts. Measures whether models rely on stereotypes when context is ambiguous. Actively used in academic research and referenced in large model evaluations. Not a live leaderboard, but the dataset is maintained.

**WinoBias.** Zhao et al. 2018. Focused narrowly on gender bias in coreference resolution (e.g., "The nurse said the doctor prescribed medicine. She said..." — does "she" refer to the nurse or the doctor?). Now considered a narrow historical reference point rather than a comprehensive bias benchmark. Largely superseded by BBQ and BOLD for new research.

**RealToxicityPrompts.** Allen Institute for AI (2020). 100,000+ prompts scraped from Reddit that might lead to toxic completion without explicitly requesting it. Scores toxicity using the Perspective API. Static dataset, not updated, but widely cited. Relevant for testing whether production deployment of a local model will generate toxic content under natural-language conditions — a valid concern for fleet models serving non-technical users like Gavin's chat system.

**BOLD (Bias in Open-Ended Language Generation Dataset).** Amazon Science (2021). 23,679 English prompts across five domains: profession, gender, race, religion, political ideology. Automated metrics include toxicity (Perspective API), sentiment (VADER), and gender polarity. As of July 2025, Amazon is still maintaining the dataset. The broadest publicly available bias benchmark for open-ended generation.

**SafetyBench.** Zhang et al. (Aug 2024). Evaluates LLM safety with multiple-choice questions in both Chinese and English, covering 7 safety categories. Useful for deployments where models are expected to behave safely across both languages. Active, with academic maintenance.

**SimpleSafetyTests (SST).** Vidgen et al. (Feb 2024). 100 simple questions across five critical safety areas: suicide/self-harm, physical violence, illegal activity, child sexual abuse material (CSAM), and cybercrime. Designed as a minimum bar — models that fail SST should not be deployed. Deliberately simple: if a model can be elicited to produce CSAM with a two-sentence prompt, no amount of benchmark performance elsewhere justifies deployment. For Hermia's context, SST tests are a logical floor-level safety gate for any new model added to the fleet.

**XSTest.** Tests the opposite failure mode from jailbreak resistance: over-refusal (exaggerated safety behavior). 250 safe prompts that well-calibrated models should not refuse (e.g., "How do I kill a process in Linux?") plus 200 genuinely unsafe contrasts. As models are increasingly safety-tuned, the over-refusal problem grows — a model that refuses to discuss "explosive" in a chemistry context is not safe, it is broken. XSTest is actively used and directly relevant to Hermia's operational context: local fleet models that over-refuse degrade the agentic workflows they are meant to power.

**StrongREJECT.** Souly et al. (Dec 2024). Addresses a specific evaluation failure: many "successful" jailbreaks produce responses that technically comply with the harmful prompt but are so vague, non-operational, or hedged as to be useless. StrongREJECT scores jailbreak success not just on whether refusal was bypassed, but on whether the resulting output actually provides harmful capability. 313 behaviors. Actively maintained. Directly relevant to any system evaluating jailbreak resistance — empty refusal bypasses are a meaningless security metric.

**TamperBench.** Feb 2026. Evaluates whether safety alignment survives fine-tuning and post-training modification. Directly relevant to Hermia's fleet context: if a user fine-tunes a local Llama model on custom data, does safety alignment persist? TamperBench is new and not yet widely adopted but addresses a real threat model.

**SafeRBench.** Nov 2025. Evaluates safety in reasoning models — models that produce explicit chain-of-thought traces. A model might refuse a harmful request in its final output while reasoning through how to accomplish it in its thinking trace. SafeRBench catches this failure mode.

---

## 4. Agentic Benchmarks

### 4.1 Summary Table

| Benchmark | Domain | Tasks | Status (May 2026) | Frontier Score | Reward Hacking Risk |
|---|---|---|---|---|---|
| SWE-Bench Verified | Code: resolve real GitHub issues | 500 verified issues | Gold standard, active | 93.9% (Claude Mythos Preview) | Moderate — SWE-bench-Live mitigates |
| WebArena | Web navigation (realistic sites) | 812 tasks, 5 websites | Active | ~60–70% top agents | HIGH — confirmed reward hacking |
| VisualWebArena | Web navigation + visual understanding | 910 tasks | Active | ~40–55% top agents | HIGH |
| OSWorld / OSWorld-Verified | Full computer use (Ubuntu/Win/Mac) | 369 tasks | Active — Verified variant (Jul 2025) | 82.6% (Holo3-35B) | Moderate — Verified mitigates |
| GAIA | Multi-tool compound reasoning, 450 questions | 450 questions | Active | 74.6% (Claude Sonnet 4.5) | Moderate |
| AgentBench | 8 diverse agent environments | 8 environments | Academic, 2023 | ~40–60% range | Moderate |
| TAU-bench | Enterprise multi-turn tool use (retail/airline) | Retail + airline domains | Active | 89.2% (Claude Mythos Preview) | Lower — policy adherence hard to hack |
| ARC-AGI-2 | Visual reasoning / fluid intelligence (agentic framing) | ~400 tasks | Active | 85% (GPT-5.5) | Low |
| Terminal-Bench | CLI / system administration tasks | Varied | Active | Frontier ~60–70% | Moderate |

### 4.2 Narrative

**SWE-Bench Verified.** The most credible agentic coding benchmark as of May 2026. Real GitHub issues from real open-source repositories; models must produce a patch that passes the existing test suite. The Verified variant (500 hand-validated issues) filters out ambiguous or poorly specified issues. SWE-bench-Live continuously adds post-2025 issues to prevent training contamination. SWE-rebench provides an independent leaderboard. The benchmark has driven massive investment in agentic coding infrastructure — the jump from ~15% (GPT-4, 2023) to ~93.9% (Claude Mythos Preview, 2026) represents one of the most dramatic benchmark progressions in AI history. Caveat: scaffold matters enormously; the same model with different scaffolding can show 20%+ variation, which limits clean model comparison.

**WebArena / VisualWebArena.** CMU's WebArena (2023) provides realistic reproductions of Reddit, GitLab, Shopify, CMS, and map environments for 812 long-horizon web navigation tasks. VisualWebArena adds visual grounding (910 tasks). Both benchmarks expose whether agents can actually navigate real web UIs. The UC Berkeley RDI April 2026 study confirmed that both can be reward-hacked by automated scanning agents achieving near-perfect scores without completing tasks. Active research is addressing this, but the reliability of published leaderboard scores is currently in question.

**OSWorld / OSWorld-Verified.** Full-stack computer use across real operating systems (Ubuntu, Windows, macOS). 369 tasks spanning file I/O, web apps, desktop apps, and cross-app workflows. OSWorld-Verified (July 2025) is a hardened variant designed to prevent gaming. As of April 2026, Holo3-35B-A3B leads at 82.6%, with Claude Mythos Preview at 79.6%. Human baseline is ~72–84%. Top AI agents now approach or exceed human-level performance on this benchmark — a significant milestone. Directly relevant to Hermia's potential future: computer-use agent evaluation for local fleet automation tasks.

**GAIA.** General AI Assistants benchmark (2023, Meta/HuggingFace). 450 questions requiring multi-step tool use — web search, file parsing, calculations, code execution — to arrive at unambiguous factual answers. Three difficulty levels. As of April 2026, Claude Sonnet 4.5 leads at 74.6%; Anthropic models hold the top six spots. GAIA is actively maintained via Princeton HAL leaderboard. One of the most realistic agentic benchmarks because the tasks are grounded in real-world compound reasoning rather than simulated environments.

**AgentBench.** THUDM (2023, ICLR 2024). Eight environments: OS interaction, database querying, knowledge graph navigation, digital card games, lateral-thinking puzzles, household planning, web shopping, and web browsing. The broadest diversity of any single agentic benchmark. Less actively updated than SWE-bench or GAIA but still cited for breadth. Scores in the 40–60% range for frontier models; the diversity of environments makes it hard to saturate.

**TAU-bench.** Sierra Research (2024). Evaluates AI agents in realistic enterprise customer service scenarios: multi-turn tool use, database interactions, and policy adherence in retail and airline domains. Critically, TAU-bench measures reliability and consistency across multiple trials (pass@1 vs. pass@k), surfacing the "reliability crisis" that single-shot benchmarks miss — an agent that succeeds 70% of the time on a customer service task cannot be deployed in production. As of May 2026, Claude Mythos Preview leads at 89.2%. TAU-bench v2 (tau2-bench) is active.

**GAIA / Terminal-Bench / FieldWorkArena.** A cluster of newer benchmarks targeting specific agentic domains (CLI tasks, structured field investigation) are active in 2025–2026 but have not yet achieved the canonical status of SWE-bench or GAIA. All are affected by the April 2026 reward-hacking findings.

**The April 2026 Reward-Hacking Crisis.** UC Berkeley's Center for Responsible Decentralized Intelligence published findings in April 2026 showing that an automated scanning agent broke all eight major agentic benchmarks — SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench, and one additional benchmark — by exploiting reward mechanisms without solving the underlying tasks. This is the most significant methodological challenge facing the agentic benchmark field. Hermia's interactive, human-in-the-loop evaluation model is structurally resistant to this failure mode: a human observer watching Hermia's TUI during a test run can verify that the agent is actually solving the task, not gaming a reward signal.

---

## 5. Security Red-Teaming Tools

*This section retains and updates the prior research from the April 2026 briefing.*

### 5.1 Summary Table

| Tool | Type | Maintained By | Open Source | MITRE/Framework | Local Support | Agentic | Key 2026 Developments |
|---|---|---|---|---|---|---|---|
| Garak | Automated vulnerability scanner | NVIDIA | Yes (Apache 2.0) | Partial | Yes | Limited | 37+ probe modules; active development |
| PyRIT | Red-teaming framework | Microsoft | Yes (MIT) | MITRE ATLAS partial | Yes | Yes (multi-turn) | Multi-modal, crescendo + TAP attacks |
| Promptfoo | CI/CD-integrated LLM testing | OpenAI (acquired Mar 2026) | Yes (MIT) | OWASP LLM Top 10 | Yes | Limited | Acquired by OpenAI; 50+ vuln types; YAML config |
| HarmBench | Standardized red-team eval | Center for AI Safety | Yes | Partial | Yes | No | Multilingual extension (Nov 2025); 510 behaviors |
| CyberSecEval 4 | Cybersecurity capability + risk benchmark | Meta (Purple Llama) | Yes | MITRE ATT&CK partial | Yes | Yes (AutoPatchBench) | CyberSOCEval (SOC automation, with CrowdStrike); AutoPatchBench |
| DeepTeam | Agentic red-teaming framework | Confident AI | Yes (MIT) | OWASP LLM + OWASP Agentic 2026 | Yes | Yes | 80+ vuln types; OWASP Top 10 for Agents 2026 |
| Scale SEAL | Private expert-evaluated leaderboards | Scale AI | No (proprietary) | Proprietary | No | Yes (PropensityBench) | 15 new benchmarks in 2025; PropensityBench (latent safety risk) |
| Mindgard | Continuous automated AI red-teaming platform | Mindgard (commercial) | No (SaaS) | MITRE ATLAS | No | Yes | Fortune 500 design partners (Jan 2026); SOC 2 Type II; Cybersecurity Excellence Award 2025 |

### 5.2 Narrative Updates

**Garak (NVIDIA).** The most depth-focused open-source scanner: 37+ probe modules, covering prompt injection, jailbreak, data leakage, toxicity generation, and model extraction. Runs entirely locally against any model served via a compatible API. The Hermia security test suite draws conceptual lineage from Garak's probe taxonomy. Key gap: Garak does not produce hardware/performance telemetry alongside security scores, and its report format is not designed for fleet-wide aggregation or Grafana export. As of May 2026, Garak is actively maintained with recent releases.

**PyRIT (Microsoft).** Python Risk Identification Tool for generative AI. Supports multi-modal attack surfaces, multi-turn attacks (crescendo: gradually escalating requests), and TAP (Tree of Attacks with Pruning). PyRIT is the most compositionally flexible red-teaming framework — it can chain attacks across model turns and supports agentic systems. Does not include hardware telemetry or fleet routing. Runs locally. Active development through early 2026.

**Promptfoo.** Acquired by OpenAI in March 2026 (terms undisclosed; remains MIT licensed and open source). YAML-configured test suites, CI/CD pipeline integration, 50+ vulnerability types, provider-agnostic. The acquisition raises questions about long-term independence but the codebase remains open. Strong enterprise adoption pre-acquisition. The OpenAI acquisition may steer roadmap toward hosted services; local-first users should monitor for divergence.

**HarmBench.** Center for AI Safety (2024). 510 standard behaviors across seven categories (cybercrime, chemical/bioweapons, copyright, misinformation, harassment, illegal activities, general harm). Standardized evaluation of 33 LLMs against 18 red-teaming methods. Multilingual extension published November 2025. PluriHarms extension (January 2026) adds continuous harm axes and personalized safety evaluation. HarmBench is the most rigorous academic red-teaming benchmark but is not a runtime tool — it evaluates fixed behavior lists, not dynamic agentic threat models.

**CyberSecEval 4 (Meta).** The most comprehensive open-source security benchmark for LLMs, part of the Purple Llama project. CyberSecEval 4 (Sep 2025) adds CyberSOCEval (SOC automation: malware analysis + threat intelligence reasoning, developed with CrowdStrike) and AutoPatchBench (automatic vulnerability patching evaluation). Tests offensive capability (code generation for attacks), defensive capability (SOC automation), and prompt injection resistance. Covers Llama, GPT, Claude, and Gemini models. For Hermia, CyberSecEval's AutoPatchBench category is a direct analog for agentic security eval of code-generating agents.

**DeepTeam.** Confident AI (November 2025). Open-source agentic red-teaming framework targeting RAG pipelines, chatbots, and autonomous LLM agents. 80+ vulnerability classes, 10+ adversarial attack strategies, OWASP Top 10 for Agents 2026 alignment. The most directly competitive tool to Hermia's security test suite: both target agentic systems, both are open-source, both map to OWASP/MITRE frameworks. Key difference: DeepTeam has no hardware telemetry, no interactive TUI, no cold-load benchmarking, and no fleet routing awareness.

**Scale SEAL.** Scale AI's Safety, Evaluations, and Alignment Lab. Operates private, expert-curated evaluation datasets to prevent overfitting. 15 new benchmarks in 2025, covering reasoning, agentic workflows, multimodal inputs, and safety alignment. PropensityBench (2025) is a novel "would-do" assessment — instead of asking "can the model do X?", it asks "would the model choose to do X given the opportunity?" in high-stakes simulated environments. SEAL leaderboards are used by major labs for pre-release validation. Not open source, not local-first, not accessible for independent fleet operators.

**Mindgard.** Commercial SaaS platform for continuous AI red-teaming. SOC 2 Type II certified, GDPR compliant, Cybersecurity Excellence Award 2025 winner. Secured Fortune 500 design partners in January 2026. Key leadership additions in September 2025 (former Rapid7 and offensive security executives). Mindgard positions as an enterprise "attacker-aligned" AI security platform — it thinks like an adversary and runs continuous automated tests. Not self-hosted, not local-first, not open source. Pricing is enterprise-tier. Hermia's differentiation against Mindgard is local-first operation and fleet-integrated telemetry, not evaluation depth.

---

## 6. Leaderboards & Meta-Evaluation Platforms

### 6.1 Summary Table

| Platform | Type | Methodology | Open Source | Status (May 2026) | Best Used For |
|---|---|---|---|---|---|
| LMSYS Chatbot Arena (arena.ai) | Human preference via pairwise voting | Bradley-Terry Elo | Partially (lmarena-ai) | Active, gold standard | Real-world preference signal |
| HuggingFace Open LLM Leaderboard | Automated benchmark aggregation | Multi-benchmark average | Yes | Retiring | Historical tracking of open models |
| Artificial Analysis | Multi-metric (intelligence + speed + price) | Composite intelligence index | No (public data) | Active | Price/performance tradeoffs |
| AlpacaEval 2.0 | Instruction-following via LLM judge | GPT-4 Turbo win rate, length-controlled | Yes | Active | Fast instruction-following comparison |
| Scale SEAL Leaderboard | Expert-evaluated private datasets | Domain expert scoring | No | Active | Pre-release model validation |
| BenchLM.ai | Aggregator leaderboard | Collects and tracks ~50+ benchmarks | No | Active | Benchmark tracking |
| llm-stats.com | Aggregator | Multi-benchmark tracking | No | Active | Quick comparisons |
| Epoch AI | Historical benchmark tracking | Literature survey | No | Active | Longitudinal capability progress |

### 6.2 Narrative

**LMSYS Chatbot Arena (arena.ai).** The most trusted preference-based leaderboard, now rebranded from the LMSYS name. Users are shown two anonymized responses and vote for the preferred one; thousands of votes are aggregated via the Bradley-Terry model (moved from online Elo in December 2023 for stability). As of May 2026, the Elo frontier spans GPT-5, Claude Opus 4.6, Gemini 3.1 Pro, Grok 4, and DeepSeek V3.2 (1,450–1,561 Elo). The Coding Leaderboard separated from the General leaderboard in 2026, recognizing that coding preference and conversational preference are distinct capabilities. Arena is the benchmark most resistant to gaming because users do not know which model they are rating. Limitation: Arena reflects user population preferences, which are not uniform — different user populations would produce different rankings.

**HuggingFace Open LLM Leaderboard.** The canonical leaderboard for open-weight models (2023–2025). Open LLM Leaderboard v2 (launched June 2024) used IFEval, MuSR, GPQA, MATH, BBH, and MMLU-Pro. Now officially retiring: "as model capabilities change, benchmarks need to follow, and the leaderboard is slowly becoming obsolete as it could encourage people to hill climb irrelevant directions." The archive remains available. The leaderboard drove enormous open-source model development but also benchmark saturation through hill-climbing. Its retirement is a significant signal: the field has no consensus replacement for open-model ranking.

**Artificial Analysis.** Commercial independent benchmarking service tracking intelligence, speed (tokens/second, TTFT), price, and context window across 357+ models. Uses GPQA-Diamond, MMLU-Pro, HumanEval+, MATH, and other established benchmarks as inputs to a composite "intelligence index." As of May 2026, GPT-5.5 (xhigh) leads with an Intelligence Index score of 60. Artificial Analysis is the best single resource for price/performance tradeoffs across API providers — critical for fleet cost modeling.

**AlpacaEval 2.0.** Stanford (2023, updated 2024). 805 instruction-following tasks; GPT-4 Turbo judges responses relative to a reference model (text-davinci-003 baseline). Length-controlled scoring addresses the known length bias. Achieves 0.98 Spearman correlation with Chatbot Arena while running in under 3 minutes for under $10 in API costs. Useful for rapid iteration during model development. Current leader: Granite 3.3 8B Base (IBM) at 62.7% — an artifact of the benchmark's sensitivity to instruction-following style rather than raw intelligence.

**Scale SEAL Leaderboard.** Described above in Section 5.2. Private datasets prevent hill-climbing. Used by major labs pre-release. Not accessible for independent evaluation.

**Epoch AI.** Tracks historical capability progress across all major benchmarks over time. Particularly useful for understanding the saturation timeline and projecting when current hard benchmarks will be saturated. Not a live leaderboard but an invaluable research resource.

---

## 7. Competitive Matrix

*Unified cross-category view. Columns represent key design properties relevant to Hermia's context.*

| Tool / Benchmark | Category | Local | Interactive | Hardware Telemetry | Fleet-Aware | MITRE/OWASP Mapped | Agentic | Open Source | Grafana/DB Export | Cold-Load |
|---|---|---|---|---|---|---|---|---|---|---|
| **Hermia** | Eval harness | Yes | Yes (TUI) | Yes (CPU/RAM; AMD GPU v0.1; NVIDIA+ASi v0.1) | No (v0.2) | Partial (tagged; structured export v0.1) | Yes | Yes | Yes (Postgres/Grafana) | Yes |
| Garak | Security scanner | Yes | No (CLI) | No | No | Partial | No | Yes | No | No |
| PyRIT | Red-team framework | Yes | No (Python API) | No | No | ATLAS partial | Yes | Yes | No | No |
| Promptfoo | LLM testing / CI | Yes | No (YAML/CLI) | No | No | OWASP | Limited | Yes | No | No |
| HarmBench | Security benchmark | Yes | No (research) | No | No | Partial | No | Yes | No | No |
| CyberSecEval 4 | Security benchmark | Yes | No (scripts) | No | No | ATT&CK partial | Yes | Yes | No | No |
| DeepTeam | Agentic red-team | Yes | No (Python API) | No | No | OWASP 2026 | Yes | Yes | No | No |
| Scale SEAL | Meta-eval platform | No | No | No | No | Yes | Yes | No | No | No |
| Mindgard | AI sec platform (SaaS) | No | No | No | No | MITRE ATLAS | Yes | No | Yes (API) | No |
| HELM | Capability benchmark | Yes | No (Python) | No | No | No | No | Yes | No | No |
| SWE-Bench | Agentic coding benchmark | Yes | No | No | No | No | Yes | Yes | No | No |
| LiveBench | Capability benchmark | No (API) | No | No | No | No | No | Partial | No | No |
| LMSYS Arena | Meta-eval (human pref) | No | No | No | No | No | No | Partial | No | No |
| Artificial Analysis | Meta-eval aggregator | No | No | No | No | No | No | No | No | No |
| AgentBench | Agentic benchmark | Yes | No | No | No | No | Yes | Yes | No | No |
| TAU-bench | Agentic benchmark | Yes | No | No | No | No | Yes | Yes | No | No |
| TruthfulQA | Safety benchmark | Yes | No | No | No | No | No | Yes | No | No |
| XSTest | Safety benchmark | Yes | No | No | No | No | No | Yes | No | No |
| StrongREJECT | Safety benchmark | Yes | No | No | No | No | No | Yes | No | No |

---

## 8. Where Hermia Sits in This Landscape

### 8.1 What Hermia Is

Hermia is an **interactive, local-first, hardware-aware LLM evaluation harness**. Its defining properties are:

- **Interactive TUI** (Python/Textual): operators select models and test suites in real time, watch results stream live
- **Live system telemetry**: CPU, RAM, GPU, VRAM during test execution — the only eval tool in this landscape that correlates test performance with hardware load (AMD GPU via sysfs; NVIDIA + Apple Silicon support shipping in v0.1)
- **Cold-load benchmarking**: measures from a clean model-load state, not a warmed inference session — captures inference startup costs, VRAM allocation patterns, and first-token latency that warm benchmarks miss entirely
- **MITRE-mapped security tests**: test cases are tagged with MITRE ATLAS references in test metadata; structured taxonomy fields and export shipping in v0.1
- **Agentic scoring**: multi-step task evaluation including tool-use chains, constraint adherence, error recovery, and routing decisions
- **Direct Ollama integration**: v0.1 tests run against a local Ollama endpoint (localhost:11434); LiteLLM gateway integration and fleet routing awareness ship in v0.2
- **Postgres/Grafana export**: results feed into the existing fleet monitoring stack — evaluation is not a one-time report, it is a continuous dashboard signal

No tool in the current market combines all of these properties. The closest competitor in any individual dimension is Garak (security breadth), DeepTeam (agentic + OWASP mapping), or Mindgard (enterprise automated red-teaming), but none has hardware telemetry, none is fleet-routing-aware, and none integrates with Grafana as a live operational signal.

### 8.2 What Hermia Is Not

Hermia is not:

- **A passive benchmark database.** It does not produce a static score for a model that gets submitted to a leaderboard. Its outputs are operational signals for a specific fleet, not publishable benchmark numbers.
- **A human-preference evaluator.** It does not use pairwise voting or LLM-as-judge scoring (yet). Its current scoring is rubric-based and deterministic where possible.
- **A research reproducibility tool.** HELM's design philosophy (reproducible, transparent, cross-model comparison at scale) is not Hermia's goal. Hermia's goal is operational readiness of a local fleet, not academic publication.
- **A cloud safety auditor.** Mindgard, Scale SEAL, and commercial AI red-teaming services target enterprise cloud API deployments. Hermia explicitly does not require cloud connectivity.
- **A comprehensive knowledge capability benchmark.** Hermia tests security behavior, agentic reasoning, and constraint adherence — not general knowledge, math competition problems, or PhD-level science questions. MMLU, GPQA, and HLE are out of scope.

### 8.3 Differentiation Summary

| Hermia Strength | Why It Matters | Who Else Has It |
|---|---|---|
| Cold-load benchmarking | Captures true inference startup cost — critical for fleet provisioning decisions | Nobody (among open-source operational eval tools) |
| Live GPU/VRAM telemetry correlated with test results (AMD v0.1; NVIDIA+ASi v0.1) | Lets operators know if a model fails a test because of capability or resource contention | Nobody (among open-source operational eval tools) |
| Fleet routing integration via LiteLLM (v0.2) | Tests will run against the actual routing layer, not a mocked endpoint — catches lane-level failures | Nobody (among open-source operational eval tools) |
| MITRE-tagged security tests (structured taxonomy export v0.1) | Security team language alignment; audit-ready output | Partial (Garak partial, Mindgard yes but closed) |
| Postgres/Grafana export | Eval as a continuous operational signal, not a one-time report | Nobody (among open-source operational eval tools) |
| Interactive TUI | Operator can make real-time decisions during a test run, not just post-hoc analysis | Nobody (among open-source operational eval tools) |

### 8.4 Gaps and Opportunities

**Gap 1: No LLM-as-judge scoring.** The industry default for conversational quality, instruction-following calibration, and safety evaluation is now LLM-as-judge (GPT-4 Turbo or similar as evaluator). Hermia's rubric-based scoring is more deterministic and auditable but cannot evaluate open-ended response quality. Adding an optional LLM-as-judge scoring layer (callable via the LiteLLM manager lane) would close this gap without sacrificing local-first principles.

**Gap 2: No XSTest / over-refusal testing.** Hermia has security boundary tests (refusal of forbidden actions) but no systematic test for over-refusal — models that refuse legitimate requests. For fleet models serving real users (Gavin's chat system, home automation agents), over-refusal is as much a failure mode as under-refusal. XSTest's 250 benign prompts would be a natural addition.

**Gap 3: No persistent model identity verification.** CyberSecEval 4 and the OWASP LLM Top 10 identify model integrity (LLM08) as a risk — the orchestrator assumes it is talking to the configured model but cannot verify. Hermia currently has no test that verifies model identity at the lane level. A hash-based or fingerprinting-based model identity test (analogous to the RAG Honeypot project concept) would close this gap.

**Gap 4: Benchmark visibility / external comparability.** Hermia's scores are meaningful within the fleet context but cannot be compared to published leaderboard scores. Adding a "calibration mode" that runs a small canonical subset of questions from MMLU-Pro, LiveBench, or GPQA-Diamond would allow fleet models to be placed on the public benchmark spectrum without requiring external API access.

**Gap 5: Reward-hacking resistance documentation.** Given the April 2026 UC Berkeley findings on agentic benchmark reward hacking, Hermia's interactive TUI model is structurally resistant (a human can verify agent behavior in real time) but this has not been documented as a design property. Formalizing this as an explicit design decision — "Hermia is human-observable by default" — is a meaningful competitive positioning for the post-reward-hacking-crisis era.

**Opportunity: SafeRBench / reasoning trace safety.** As fleet models increasingly use extended thinking (CoT), evaluating whether safety alignment holds across reasoning traces (not just final outputs) is a genuine gap. SafeRBench (Nov 2025) has identified this problem; Hermia could be the first local-first tool to operationalize it.

**Opportunity: TAU-bench style reliability scoring.** TAU-bench's pass@k reliability metric — running the same test multiple times and measuring consistency — is directly applicable to fleet model evaluation. A model that succeeds 70% of the time on a home automation task is not suitable for production. Adding reliability (pass@5 or pass@10) as a first-class metric alongside single-run scores would meaningfully differentiate Hermia's output from all static benchmarks.

---

## Appendix A: Key Saturation Reference

| Benchmark | Launch Year | Saturation Date (approx.) | Top Score at Saturation |
|---|---|---|---|
| MMLU | 2020 | 2024 | 88–90% |
| HumanEval | 2021 | 2024 | 95%+ |
| GSM8K | 2021 | 2024 | 99% |
| MATH (full) | 2021 | 2025 | 95%+ |
| BIG-Bench Hard | 2022 | Approaching 2026 | 88.9% |
| GPQA-Diamond | 2023 | Approaching 2026 | 94.3% |
| MMLU-Pro | 2024 | Approaching 2026–2027 | 89.8% |
| HLE | 2025 | Not yet | 44.7% |
| ARC-AGI-2 | 2025 | Not yet | 85% |
| LiveBench | 2024 | Not yet | <70% |
| SWE-Bench Verified | 2024 | Not yet (hard) | 93.9% |

---

## Appendix B: Research Notes

- HELM entering maintenance mode: confirmed June 1, 2026 (Stanford CRFM official announcement)
- HuggingFace Open LLM Leaderboard: officially retiring per HF Space discussion thread (confirmed)
- Promptfoo acquired by OpenAI: March 2026; remains MIT licensed per announcement
- CyberSOCEval (CyberSecEval 4 extension with CrowdStrike): announced Fal.Con 2025, September 15, 2025
- UC Berkeley reward-hacking study: published April 12, 2026 (RDI)
- ARC-AGI-3: planned for 2026 release per ARC Prize official site
- MMLU-ProX (multilingual): EMNLP 2025 Main track

---

*Sources are listed inline. Key leaderboard data sourced from llm-stats.com, benchlm.ai, artificialanalysis.ai, and direct benchmark project pages as of 2026-05-10.*
