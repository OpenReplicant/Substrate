# BDI agent architectures combined with LLMs, 2024-2026

Method note: checked 2026-11-23 with web search, GitHub/PyPI APIs and the papers' own PDFs (read via pdftotext). Licences and dates below are from the GitHub API "license" field unless stated. Not covered by any source I could read: the survey arXiv 2509.02515 (PDF unreadable to the fetcher; only a search-snippet description). Many search-summary claims were cross-checked against the PDFs; unverified items are in Gaps.

## 1. Main LLM+BDI systems 2024-2026: what the LLM does vs what BDI does

### Takeaway
The literature is small, mostly workshop/extended-abstract level, and splits into three patterns: (a) LLM as natural-language interface to a BDI agent (ChatBDI), (b) LLM as runtime plan/belief generator into a BDI plan library (Ciatto et al. ECAI 2025; Jarvis; Utah report), (c) LLM inside a rule-based BDI shell for believability (child-helpline agent). Measured evidence is thin: tiny samples, single domains, no head-to-head against plain LLM agents found.

### Cited Findings
- ChatBDI (Gatti, Mascardi; AAMAS 2025 extended abstract): Jason inside JaCaMo "thinks"; CodeGemma "talks" and, with nomic-embed-text embeddings, "understands" (human message embedded and compared with the agent's context, mapped to the closest KQML literal). A meta-programming "chattification" injects plans into existing agents without touching their source. The LLM does not generate plans. Authors say the closest prior work is Frering et al. (closed source, only maps text to a predefined goto(X,Y)), and that Ricci et al. (AAMAS 2024 Blue Sky) only envisioned generative BDI. No quantitative evaluation in the abstract — [ChatBDI PDF](https://aamas.csc.liv.ac.uk/Proceedings/aamas2025/pdfs/p2541.pdf). Code: [VEsNA-ToolKit/chatbdi](https://github.com/VEsNA-ToolKit/chatbdi), last push 2026-01-08, 4 stars, GitHub shows no licence file (so default all-rights-reserved; do not reuse without asking) — GitHub API. The paper itself is CC BY 4.0.
- Generative BDI plan generation (Ciatto, Aguzzi, Battistini, Baiardi, Burattini, Ricci; ECAI 2025, FAIA 413): extends AgentSpeak(L) with a plan-generation procedure (PGP) working on demand, reactively after plan failure, or proactively; prototyped in JaKtA (a Kotlin Jason-like BDI technology). The agent spec carries natural-language descriptions of admissible goals/beliefs/actions; the LLM writes plans, the BDI cycle executes them and retracts on failure — [paper PDF](https://cris.unibo.it/bitstream/11585/1026414/3/FAIA-413-FAIA251223.pdf), [abstract page](https://apice.unibo.it/xwiki/bin/view/Publication/PlanGenerationBDIEcai2025). Measured: reactive PGP only, grid-world "reach home" task, 4 LLMs x 5 runs = 20 runs. Task Success Rate: GPT-4.1 100%, a second model 60%, DeepSeek V3 40%, Gemini 2.5 Pro 20% (the paper labels the 100% model "GPT-4"; Claude 3.7 thinking's figure was not clearly captured by my text extraction — check the PDF table). Plan-quality metrics included generalization count, redundancy, novel invented goals/beliefs, semantic misalignment. Experiment code: [pslab-unibo/experiment-2025-ECAI-generative-bdi-agents](https://github.com/pslab-unibo/experiment-2025-ECAI-generative-bdi-agents), Apache-2.0, last push 2025-08-05. Paper is CC BY-NC 4.0 (text).
- Jarvis (Raupp, Paulo, Chagas, UFSC; WESAAC workshop 2026): a CArtAgO artifact + two Jason internal actions. At runtime it introspects artifacts in the workspace (operation signatures, observable properties, natural-language manual), prompts an LLM for an AgentSpeak plan library, validates against discovered operations/arity/subgoals, injects surviving plans and beliefs. Case study: three agents, an air-conditioner artifact; with gpt-4.1-mini at temp 0.2 repeated runs gave a syntactically valid plan library on the first call, every AirConditioner plan accepted; about 1.5K input and 200 output tokens per learning episode. Authors explicitly do not claim: semantic safety (mode preconditions), reactive/proactive generation, failure-driven plan retraction, generality — [Jarvis PDF](https://sol.sbc.org.br/index.php/wesaac/article/download/45248/45009/), [abstract](https://sol.sbc.org.br/index.php/wesaac/article/view/45248). The paper credits Aguzzi et al. 2025 ("PlanchBDI") with unifying chattification and plan generation; I found only that one-line description of PlanchBDI. No repository link in the paper text.
- Self-aware BDI agent (Lawton, Sacharny, Henderson; Univ. of Utah tech report UUCS-26-001, 15 May 2026): full LLM-driven deliberation loop; LLM generates parameterized natural-language plan templates with role slots (no hand-authored plans), matches plans to beliefs via NLI, produces machine-verifiable satisfaction conditions with a three-tier verification, refines the plan library across rounds from environmental feedback and exports it to seed new agents. Eval: 53 GAIA level-1 questions, Qwen3-8B via vLLM: 13.2% (any round, simulation mode), 9.4% for both seeded and non-seeded single pass; authors say seeding improves reasoning structure but not raw accuracy, and that web-search/tool use is the bottleneck. Preliminary; no code link found in the text — [UUCS-26-001](https://www-old.cs.utah.edu/docs/techreports/2026/UUCS-26-001.pdf).
- Hybrid BDI-LLM child-helpline trainer (Al Owayyed, Denga, Brinkman; IVA 2025, arXiv 2509.16784): LLMs added to a rule-based BDI for intent recognition, response generation and a bypass; Study 1 LLM components non-inferior to human-crafted responses; Study 2 (n=37, within-subject) hybrid rated more believable than rule-based; engagement effect inconclusive (posterior 0.845, 95% HDI [-0.149, 0.465]). Code availability not stated — [arXiv](https://arxiv.org/abs/2509.16784).
- astra-langchain4j (Collier, Beaumont, Ciortea; arXiv 2601.21879): ASTRA agent language (not Jason) gets an LLM module built on LangChain4j; examples include tic-tac-toe with LLM players. Code at gitlab.com/astra-language/astra-core and Maven Central `com.astralanguage:astra-langchain4j`; licence not stated in what I could read; I could not extract the paper body — [arXiv PDF](https://arxiv.org/pdf/2601.21879).
- Related, by description only: NatBDI (Ichida et al.) matches natural-language plans to beliefs with NLI and falls back to reinforcement learning — cited in the ChatBDI paper above. Cetana (PyPI 0.1.0, "auditable BDI agents for the LLM era") is early-stage — [search listing](https://pypi.org/project/cetana/); not inspected.
- Survey: arXiv 2509.02515 "Contemporary Agent Technology: LLM-Driven Advancements vs Classic Multi-Agent Systems" mentions BDI+LLM hybrids; I could not read it — [arXiv](https://arxiv.org/pdf/2509.02515).

### Inferences
- The only quantified result on LLM-written BDI plans (Ciatto) shows large model dependence (20%-100% success on one simple task, N=5 per model); BDI structure does not remove the dependence on the planner model, but gives validators (admissible goals/beliefs, arity checks) and failure-driven retraction.
- No source I found shows BDI+LLM beating a plain tool-calling LLM agent on a standard benchmark; the Utah GAIA numbers are low and not compared to a baseline.
- Common pattern worth copying: the LLM proposes into a typed vocabulary, a symbolic validator filters, the BDI layer owns commitment (what is being pursued) and retraction on failure.

### Gaps
- No full text of the survey 2509.02515; no details of PlanchBDI (Aguzzi et al. 2025) beyond one line; Frering et al. not located; JaKtA repo/licence not verified (the guessed GitHub path 404'd); ChatBDI licence absent.
- No head-to-head vs non-BDI LLM agents found.

## 2. Jason, JaCaMo, CArtAgO today

### Takeaway
All three are alive, Java/JVM, and usable over a network only through bridges you write; no native Python API was found. Jason and JaCaMo are LGPL-3.0 (acceptable); CArtAgO is reported GPL-3.0 by the GitHub API (needs separate-process treatment, and check the LICENSE file directly since older CArtAgO releases were LGPL by my memory — unverified).

### Cited Findings
- Jason: latest release v3.3.3, published 2026-10-15 (previous v3.3.0 on 2024-02-21); LGPL-3.0; last push 2026-10-30; 262 stars; Java — [GitHub release API](https://api.github.com/repos/jason-lang/jason/releases/latest), [repo](https://github.com/jason-lang/jason).
- JaCaMo: latest release v1.3.1, published 2026-08-31; LGPL-3.0; last push 2026-10-16; 20 stars — [releases API](https://api.github.com/repos/jacamo-lang/jacamo/releases/latest), [repo](https://github.com/jacamo-lang/jacamo).
- CArtAgO: GPL-3.0 per GitHub API; last push 2024-07-15; tags up to v3.1 — [repo API](https://api.github.com/repos/CArtAgO-lang/cartago). The latest-release endpoint returned 404 (tags only).
- Integration pattern for LLMs: Jarvis shows an LLM endpoint can be wrapped as a CArtAgO artifact exposing operations and publishing usage metrics as observable properties; ChatBDI uses KQML messages as the bridge — sources in section 1.
- CArtAgO is the framework for the Agents and Artifacts model — environment as workspaces containing agents and artifacts — [CArtAgO chapter listing](https://apice.unibo.it/xwiki/bin/view/Publication/CartagoE4masIII).

### Inferences
- Use from Python: no evidence of a maintained Python binding; practical routes are a JVM sidecar with a message/HTTP bridge (e.g. a CArtAgO artifact, which Jarvis already shows for an LLM, could front HTTP/Postgres), or reimplement the cycle in Python. Treat as unverified design option, not a documented feature.
- GPL CArtAgO could only be a separately run service under the repo's rule S-146.

### Gaps
- Did not verify CArtAgO's current LICENSE file text or JaCaMo REST/web interfaces; did not check Jason's own documented Python/network interfaces.

## 3. Agents & Artifacts (A&A) meta-model and LLM use

### Takeaway
A&A models the environment as first-class artifacts in workspaces, which maps closely onto "everything is an object". Its only direct LLM use I found is Jarvis (artifact introspection as the grounding substrate for LLM plan generation).

### Cited Findings
- Jarvis states artifacts "already represent environmental affordances through operation signatures, observable properties, and often a natural-language description", and argues planning over artifacts discovered live aligns the LLM's action model with CArtAgO's environment model rather than a design-time action list — [Jarvis PDF](https://sol.sbc.org.br/index.php/wesaac/article/download/45248/45009/).
- Jarvis's introspection works "without binding to a live workspace" and the Jarvis artifact itself publishes accepted/rejected-plan and token counts as observable properties — same PDF.
- A 2023 AAMAS paper describes a hypermedia platform where infrastructure executes computational artifacts as defined in the JaCaMo meta-model — [AAMAS 2023 p2499](https://www.southampton.ac.uk/~eg/AAMAS2023/pdfs/p2499.pdf) (title not read; from search listing). A vision paper on LLMs filling information gaps in hypermedia MAS exists (via search summary; not opened).

### Inferences
- From background knowledge (not sourced here): A&A concepts are artifacts with usage interface (operations), observable properties (state agents perceive as beliefs), signals (events), workspaces (scoping), and focus (subscription). These line up with the design's objects/properties/actions/events; permission gates and Postgres-as-blackboard are not part of A&A. Verify against the CArtAgO docs before citing.

### Gaps
- Official A&A/CArtAgO documentation not fetched; no LLM paper beyond Jarvis found using A&A.

## 4. Plan learning/compilation from experience

### Takeaway
Classic BDI learning exists (learning plan context conditions from experience) but I found no 2024-2026 system that compiles LLM episodes into BDI plans with Soar-style chunking and measured evidence. Closest: the Utah plan-library refinement, Ciatto's reactive generation, Jarvis's persistent generated plans.

### Cited Findings
- Utah agent: refines plan library over rounds with failure feedback and seeds other agents; no accuracy gain from seeding (9.4% vs 9.4%) on 53 GAIA questions with Qwen3-8B — [UUCS-26-001](https://www-old.cs.utah.edu/docs/techreports/2026/UUCS-26-001.pdf).
- Ciatto et al.: plans generated after plan failure (reactive) and retracted on failure; Jarvis keeps generated plans until termination (no retraction) — sections above.
- Older learning in BDI (Singh, Sardina, Padgham): learn plan selection/context conditions from experience, not new plans — [IJCAI 2011](https://ijcai.org/proceedings/2011/420), via search listing.

### Inferences
- The evidence that distilled plans improve a model's accuracy is weak so far; what plan libraries reliably give is structure, auditability and cheaper reuse (about 1.5K input tokens once per learned plan in Jarvis).

### Gaps
- No Soar-chunking-with-LLM or case-based BDI+LLM paper found; not searched in the Soar literature (outside BDI scope).

## 5. Python-native BDI frameworks

### Takeaway
MASPY (MIT, active) is the best-fit Python BDI framework; SPADE-BDI is a BDI layer on XMPP-based SPADE; neither has LLM-specific evidence.

### Cited Findings
- MASPY (laca-is/MASPY): Python BDI MAS framework with AgentSpeak-like declarative style; MIT; last push 2026-11-13; 27 stars; 21 open issues — [GitHub API](https://api.github.com/repos/laca-is/MASPY), AAMAS 2026 paper YIGW5980 describes it (via search summary; PDF unreadable).
- SPADE_BDI: PyPI 0.3.3, uploaded 2026-07-28; runs AgentSpeak ASL files with KQML performatives; fork javipalanca/spade_bdi is MIT, pushed 2026-09-01; original upstream sfp932705 has no clear licence and last push 2022 — [PyPI](https://pypi.org/pypi/spade_bdi/json), [fork API](https://api.github.com/repos/javipalanca/spade_bdi). Depends on the SPADE/XMPP stack.
- PROFETA (Python, BDI robotics), agent-bdi, cetana (0.1.0) surfaced but were not verified — [search results](https://pypi.org/project/agent-bdi/).

### Inferences
- For Postgres-blackboard design, a hand-rolled cycle (belief/goal/intention tables, plan library as rows) is likely lighter than adopting MASPY or SPADE, whose runtimes own their own belief stores; MASPY is the one to read for semantics.

### Gaps
- Did not inspect MASPY's code, tests, release cadence or LLM support; PROFETA licence/maintenance unchecked.

## Overall answer to "does BDI give a proven structure?"
Proven as a structure of explicit beliefs, desires, intentions and plan libraries in agent programming (decades), but not proven with LLMs: 2024-2026 LLM+BDI work is prototype-scale (single domains, N=5-53 items, no strong baselines). What the papers do demonstrate: (1) typed vocabulary plus validator before an LLM-authored plan enters the library, (2) failure-driven plan retraction, (3) artifacts' operation signatures and observable properties as the grounding for LLM plan generation, (4) LLM-quality dependence is large.
