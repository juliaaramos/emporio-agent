# Empório da Música — customer service agent

🇧🇷 [Versão em português](README.pt-BR.md)

A text-message agent prototype that serves customers of Empório da Música (a fictional musical instrument store in Campo Grande, MS, Brazil): catalog, prices, promotions, payment, shipping, order status, exchanges and returns, opening hours and store information.

The agent talks to customers in Brazilian Portuguese, because that is the store's audience. The code, tests and this documentation are in English; the example conversations in [`examples/`](examples/) are in Portuguese, as the agent produced them.

The core idea: **the LLM talks and decides what to look up; the code looks up and calculates.** Prices, installments, shipping, return deadlines and identity checks are done in Python, with tests. The model never does arithmetic, never resolves data conflicts and never receives amounts in reais as arguments.

---

## How to run

Requirements: Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # Windows: copy .env.example .env
python scripts/configurar_chaves.py   # writes the keys to .env without displaying them
```

### Model provider

Any OpenAI-compatible API works. There are four ready-made profiles (`LLM_PROVIDER` in `.env`, or `--provider` on the command line):

| Profile | Default model | Key | Cost |
|---|---|---|---|
| `groq` (default) | openai/gpt-oss-120b (open-weights model served by Groq) | `GROQ_API_KEY` ([console](https://console.groq.com/keys)) | free tier, no credit card |
| `gemini` | gemini-3.5-flash | `GEMINI_API_KEY` ([AI Studio](https://aistudio.google.com/apikey)) | free tier (20 requests/day) |
| `ollama` | qwen2.5:3b | none ([ollama.com](https://ollama.com), then `ollama pull qwen2.5:3b`) | local |
| `openai` | gpt-4.1-mini | `OPENAI_API_KEY` | paid |

For another endpoint, set `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`. If the free Groq tier rejects requests because of the output-tokens-per-minute limit (it happens with `qwen/qwen3.8-27b`), set `GROQ_MAX_TOKENS=900`. Keys are read **only from the project's `.env`**, never from the machine's environment variables, so a key from another project is not used by accident. `.env` is in `.gitignore`; never commit keys.

### Commands

```bash
python -m emporio.cli                     # chat
python -m emporio.cli --trace             # shows every tool call and the token usage
python -m emporio.cli --provider groq     # picks the provider
python -m emporio.cli --resume            # resumes the last conversation (history in SQLite)

pytest                                    # deterministic tests (no network, no key)
python -m emporio.eval                    # golden set against the LLM (3 runs per case)
python -m emporio.eval --provider gemini groq ollama --runs 1 --pause 5   # compares providers
python scripts/gerar_exemplos.py          # regenerates examples/*.md
python -m emporio.data_quality            # data quality report
```

### Reference date

The data ends on 2026-03-22. With the real clock, every pending order would look stalled for months and every return deadline would have expired. So `.env` sets `REFERENCE_DATE=2026-03-25` and `REFERENCE_TIME=10:30` (a Wednesday, store open), the store's "now". Leave them empty to use the real clock. On that date no delivered order is within the 7-day withdrawal window; the case where a return is accepted is covered by a test with another date (`test_return_accepted_with_other_reference_date`).

---

## Technical decisions

### Approach: function calling with deterministic tools

12 typed tools over SQLite (tool names are kept in Portuguese, as the agent uses them in the store's domain language):

| Tool | What it does |
|---|---|
| `buscar_produtos` | accent-insensitive, typo-tolerant search; original and current price, active promotion, availability, data-quality alert |
| `detalhar_produto` | description, specs and ended promotions (to answer "is that promotion still valid?"); also checks whether a requested quantity can be met without revealing the stock count |
| `listar_promocoes_ativas` | only what is active in the system, optionally by category |
| `calcular_pagamento` | takes only product codes and quantities; applies promotion, non-cumulative PIX discount, minimum-installment bands and rounding |
| `calcular_frete` | metropolitan-area rule, or PAC/SEDEX/Jadlog lead times |
| `verificar_cliente` | e-mail + (order number or last 4 digits of the phone); stores the customer in the session state |
| `listar_pedidos_do_cliente`, `consultar_pedido` | only the verified customer's orders; the check is in code |
| `avaliar_devolucao` | computes withdrawal, preference exchange, defect exchange and legal warranty for an order, and tells the model the next step |
| `consultar_politica` | the exact text of one manual section (closed list) |
| `info_loja` | contacts, hours and whether the store is open now (national and MS holidays) |
| `encaminhar_humano` | opens a ticket with a protocol number and a 24-business-hour return time |

**Why not text-to-SQL:** there are 6 small tables and predictable questions. Model-generated SQL would add risk (leaking another customer's data, getting a sum wrong) with no real gain.

**Why not vector RAG:** the manual is about 3k tokens with well-defined sections. It was extracted once to [`data/policies.md`](data/policies.md), split by section, and the `consultar_politica` tool takes the section from a closed list. There is no retrieval failure, and every policy lookup is logged, which makes it possible to measure whether the agent *knows when to consult policies*, one of the challenge's criteria. A test checks sentence by sentence that `policies.md` matches the PDF. Putting the whole manual in the prompt would also work, but then that behavior could not be measured.

**Why no framework (LangChain etc.):** the function-calling loop is ~100 lines ([`agent.py`](src/emporio/agent.py)). Explicit code is easier to debug, to test with a fake client and to move between providers.

### Security by construction, not by prompt

- The verified customer lives in the session state, injected by the code. The model cannot pass a `customer_id`; if it tries, the call is rejected.
- Another customer's order returns "not found in your account", without revealing that it exists.
- Verification is limited to 3 attempts with a generic message (it does not reveal whether an e-mail exists).
- Tools return only the first name, never phone or e-mail.
- Verification is not persisted: when a conversation is resumed, the customer identifies again.
- The exact stock quantity never reaches the model, because it is internal store information. Search says only "available" or "last units". If the customer asks "do you have 3?", `detalhar_produto` receives the quantity and answers yes or no without revealing the number.
- A ticket's summary is assembled by the code from the order record; the model only describes what the customer said. There is one open ticket per order and session.

### Prompt strategy

[`prompts/system.md`](src/emporio/prompts/system.md): the persona from §7.1 ("a friend who knows music"), the 5-step flow from §7.2 and non-negotiable rules (no price, deadline or policy without a tool; a promotional price always shown with the original price and percentage; the system, not the calendar, says whether a promotion is valid). The prompt receives the date, the time and whether the store is open, to announce when human service resumes outside business hours (§7.1). Tool descriptions are prompt too: they say when to use each one.

Tool responses carry contextual instructions (e.g. `alerta_cadastro`, `nota_de_interpretacao`, `proximo_passo` for returns, `instrucao` for late orders). The rule reaches the model at the moment it matters, without inflating the system prompt.

### Model choice

Self-imposed constraint: the project had to run **at no cost**, so any reviewer can test it. I compared three free options on the golden set (table in [Results](#results)):

- **Groq / gpt-oss-120b — chosen.** Best result by a wide margin (22/25 cases, 31/33 turns with the right tool), follows the verification protocol and cites manual sections. Open-weights model: it can be moved to another provider or run locally with suitable hardware.
- **Gemini 3.5 Flash.** Answers well in ad-hoc tests, but the free tier has a quota of 20 requests/day per model, not enough even for one evaluation run.
- **Ollama / qwen2.5:3b (local).** The only one that fit on an 8 GB machine without a GPU. It does not follow the tool protocol (4/25). Kept as a no-key option, with the limitation documented.

The architecture does not depend on the model: switching is one line in `.env`, and the golden set measures the impact of the switch.

### Interface and memory

CLI with `rich` (the challenge prioritizes the agent working correctly). History is persisted in SQLite per session (`data/sessions.db`), with a window of the last 40 messages sent to the model without ever separating a tool call from its result. Tickets go in a `tickets` table.

---

## Evaluation

- **Deterministic tests** (`pytest`, 60 tests, no network): data quality, fidelity to the manual, every tool and edge case, and the agent loop with a fake LLM.
- **Golden set** ([`tests/eval/golden.yaml`](tests/eval/golden.yaml)): 26 development cases + 5 held-out cases (holdout) that were not used to tune the prompt. It includes multi-message conversations. For each turn the evaluator checks: tools called, a policy answered without `consultar_politica` (counts as a failure), R$ amounts extracted from the reply against the expected values (including forbidden values, such as PIX stacked with a promotion) and refusals. Each case runs 3 times at temperature 0 and passes only if it passes all 3. An LLM judge is optional (`--judge`) and only evaluates tone. The `quantidade_em_estoque` case was added after the comparison below (which uses the original 25 cases); it passes with qwen/qwen3.8-27b and has not yet been run on gpt-oss-120b.

### Results

Golden set with 1 run per case (details and reading in [`eval_results/comparacao.md`](eval_results/comparacao.md)):

| Provider / model | Dev cases (25) | Holdout (5) | Right tool per turn | Median latency |
|---|---|---|---|---|
| **Groq / gpt-oss-120b** | **22/25** | **4/5** | **31/33** | 18.4 s |
| Ollama / qwen2.5:3b (CPU) | 4/25 | 0/5 | 11/33 | 8.7 s |
| Gemini / 3.5 Flash | invalid: daily quota exhausted (33 provider errors) | — | — | — |

What the failures taught (and what changed):

- **Tool, not prompt:** the local model classified "Takamine GD20" as a guitar and the search came back empty. The search now retries without the category. The same reasoning led to exposing ended promotions already in the search result, so "is that promotion still valid?" is answered with data rather than by deduction.
- **A real communication error:** in the return case, the model received `elegivel: false` with warranty until 2026-01-23 and still suggested that a defect exchange was possible. The prompt now says to follow the `elegivel` field strictly, and the tool now returns the next step and ready-made phrasing for deadlines (ended vs. still valid).
- **Errors seen in the example conversations, fixed in the tools:** the model wrote the customer's full name in the ticket, deduced from the e-mail, and confused the order date with the shipping date. Now the code builds the order data in the ticket and the model only describes the customer's request. When suggesting "other guitars on promotion", the model included the discount of a ukulele; `listar_promocoes_ativas` now filters by category. The model also opened a ticket without asking and then a second ticket for the same order: the tool now returns the existing protocol instead of duplicating, and the late-order instruction says to ask first. Portuguese mistakes ("Chamei aberto") led the tools to return ready-made phrases for deadlines and protocols.
- **Provider robustness:** Groq validates the generated tool call and returns 400 when it is malformed; the agent retries the call once.
- **Evaluator bug:** the model wrote "e‑mail" with a Unicode hyphen; text normalization now handles Unicode hyphens.
- **Holdout not used for tuning:** the data-deletion request (§9) was treated as out of scope. Recorded as a known failure, with no prompt adjustment.

Limitation of the evaluation itself: Groq's free tier allows 200k tokens/day per model and a full run uses ~235k, so the planned 3 runs did not fit in one day. The fixes were validated with targeted runs of the affected cases; a full 3-run evaluation is the next step.

### Example conversations

Five real conversations in [`examples/`](examples/) (in Portuguese, the agent's language), generated by `scripts/gerar_exemplos.py` with the trace of tool calls (a "Rastro das ferramentas" block in each turn). Nothing was edited by hand.

| File | Scenario |
|---|---|
| [01_catalogo_violoes](examples/01_catalogo_violoes.md) | Acoustic guitars up to R$ 1,000 and an out-of-stock product with alternatives |
| [02_precos_e_promocoes](examples/02_precos_e_promocoes.md) | Ended promotion, active promotion, non-cumulative PIX and 12 installments |
| [03_devolucao_fora_do_prazo](examples/03_devolucao_fora_do_prazo.md) | **Non-trivial case:** customer verification, computed deadlines, expired legal warranty and manufacturer warranty |
| [04_pedido_atrasado](examples/04_pedido_atrasado.md) | Late order looked up in real time and a ticket opened |
| [05_fora_de_escopo_e_loja](examples/05_fora_de_escopo_e_loja.md) | Accessories, an out-of-scope question, address and opening hours |

All were generated with the default model (`openai/gpt-oss-120b`). To regenerate all: `python scripts/gerar_exemplos.py groq`; for one: `python scripts/gerar_exemplos.py groq 04_pedido_atrasado`. The script does not save conversations in which the provider failed.

---

## Data quality and assumptions

The original CSVs stay untouched in `data/raw/`; the system uses a treated copy (`data/emporio.db`, generated by `python -m emporio.ingest`).

| # | Problem | What was done | In production |
|---|---|---|---|
| 1 | Products 135 to 144 look like automatic registrations: generic name ("Bass 3X"), brand in the name different from the description in 7 of them, specs that contradict the description (137: 5 strings × 4; 139: Poplar × Maple; 142: 88 × 61 keys; 135: Alder × Ash) and atypical prices (bass at R$ 441) | Detected in code by four signals → `data_quality_flag = cadastro_em_revisao`. The agent gives name, price and availability (system data, §7.1) but does not state specs or description and says the team will confirm | Automatic alert to the catalog owner to fix it at the source |
| 2 | 96 active with no stock; 113 discontinued; 136 discontinued with 13 units | Availability = status + stock. Discontinued is never offered, even with stock (§7.3); suggests alternatives | An ERP rule preventing the inconsistent state |
| 3 | 130 `coming_soon` appears in order 3, already delivered | Agent says "coming soon" and does not sell; inconsistency goes in the report | Review the status with the team |
| 4 | Recorded total ≠ sum of items (order 3: 3,450 × 3,498; order 20: 1,400 × 1,488) | Shows the recorded total, without recalculating (there may be an unrecorded discount) | Store discount/shipping per order |
| 5 | Repeated promotions (93, 96, 99), none with an expiry | Only `is_active=1` counts, one per product (the highest discount) | Start/end dates on promotions |
| 6 | Phone/WhatsApp: §1.2 says (67) 3341-4444; §7 says WhatsApp (67) 3321-4500. E-mail has an accent in §1.2 | 3341-4444 as phone, 3321-4500 as WhatsApp (§7 is more specific); e-mail without accent (the cover has none) | Confirm with the store |
| 7 | Payment table: "minimum installment R$ 100"; §3.1 details bands; "no minimum (except below R$ 50)" is ambiguous | Follows §3.1: up to 3x ≥ R$ 50; 4x–6x ≥ R$ 80; 7x–12x ≥ R$ 100. Installments with cents are truncated and the last one absorbs the difference. Combined payment only above R$ 2,000 | Confirm with finance |
| 8 | E-mail bruno.martins@jmail.com on two customers (11 and 43) | Verification with e-mail + a second factor (order or phone ending), which disambiguates | Unique e-mail in the registry |
| 9 | Data ends in 03/2026 | `REFERENCE_DATE` (see above) | Real clock |
| 10 | PIX 5% does not stack with a promotion (§6.2) | Fixed rule in `calcular_pagamento`, per item | — |
| 11 | The manual mentions wind instruments and 300+ instruments; the database has 65 and no wind instruments | "We don't currently have this type of instrument available", never "we don't sell it" | — |
| 12 | §4.2: defect within 30 days of purchase; §8.1: 90-day legal warranty from receipt (consumer code) | The most protective rule applies: the store handles a defect until the later of the two deadlines; afterwards, manufacturer warranty with the store's intermediation (§4.2, §8.2) | Review the manual |
| 13 | §4.1 (withdrawal) applies only to online purchases | An order with a tracking code = online. Without a real delivery date, the deadline counts from the estimated delivery date (the customer is told) | Record the delivery date and sales channel |
| 14 | §6.1 mentions Black Friday and Musician's Week; none active | Only the system counts; if asked, the agent says transparently that it is not active and shows the current price (§7.3) | — |

Other assumptions: the Campo Grande metropolitan area (§5.1) was treated as Campo Grande only (the manual does not list the municipalities); an order of exactly R$ 500 gets free shipping (the manual says "above" and "below"); the 7 days for preference exchange (§4.3) count from receipt; basses, drum kits and keyboards may require special freight outside the region (§5.2).

---

## Known limitations and next steps

- **Real authentication:** e-mail and phone are not secrets. In production, a one-time code by WhatsApp/e-mail (OTP).
- **WhatsApp integration** (the main channel in §7) through the official API, with session state per number.
- **Municipal holidays** of Campo Grande and special hours (§2) in a configurable table.
- **Real shipping quotes** by postal code (Correios/Jadlog).
- **Observability:** log every tool call, latency and cost; alert when the agent answers without looking anything up.
- **Continuous evaluation in CI** with the golden set, more adversarial cases and an LLM judge calibrated with human ratings.
- **Tickets and data-quality alerts** integrated with the team's system, instead of a local table.
- **Privacy (LGPD):** the SQLite history contains personal data. In production: a defined retention period (e.g. 90 days), anonymization afterwards, encryption at rest and handling of deletion requests (§9).

---

## Use of coding assistants

I work with **spec-driven development**: I do all the requirements gathering and root cause analysis (RCA) of the problems before writing code, and only then start developing. In this project I used **Claude Code** (VS Code extension) as an implementation assistant. The workflow was:

1. **Requirements gathering.** Before any code, I wrote an action plan: reading the brief, the CSVs and the policy manual; an inventory of the data-quality problems and how to handle each one; architecture, tools, evaluation criteria (golden set) and the example-conversation scenarios, with the numbers checked against the data.
2. **Specification validated before implementing.** I asked the assistant to challenge the plan against the brief. The gaps it found went into the specification before any code: a tool to compute return deadlines (the model never does arithmetic), exposing ended promotions to answer "is that promotion still valid?", and a fixed time of day so tests are reproducible.
3. **Implementation from the specification.** The code and tests were developed with Claude Code, following the plan. The product and risk decisions were mine: nothing published without my review, free providers only, no corporate key, keys kept out of code and chat (written to `.env` by a local script) and the held-out golden-set cases kept out of prompt tuning.
4. **RCA on every failure.** I tested the agent by chatting with it and by running the golden set. Each problem was classified (model, provider, evaluator or data) and fixed at the cause, preferably in a tool rather than in the wording of the reply. Examples: the exact stock quantity no longer reaches the model, the ticket summary is built by the code, duplicate tickets are blocked and warranty deadlines come with ready-made phrasing. The example conversations were regenerated after the fixes, never edited by hand.
