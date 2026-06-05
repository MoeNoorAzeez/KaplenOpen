# Kaplen — Platform Overview

> *A production AI platform for education, content creation, and the written word — built in 32 days at USD 500 with no code written directly.*

---

## What This Document Is

This document presents Kaplen from every angle at once: what it does for teachers, what it does for writers, what it does for content creators — and how it came to exist. The "how it came to exist" part is unusual enough to serve as the framework for everything else. Kaplen is not just a platform. It is a documented proof of a new kind of engineering.

The research paper *"Engineering Without Coding: A Practitioner Study of Operator-Driven AI Development"* (Azeez, 2026) uses Kaplen's construction as its primary case study. That paper's findings are quoted throughout this document because they describe what Kaplen *is* at the structural level — not just what it does.

---

## Part I — The Research Claim

### Engineering and Coding Are Separable Skills

> *"In this specific case, the operator's engineering competence and coding ability functioned as separable: the operator exercised engineering judgment through prompting, phase management, consolidation decisions, and architectural specification, while delegating all implementation."*
> — Azeez (2026), §7.1

The standard model of software development assumes you need both: engineering judgment to decide what to build, and coding ability to build it. Kaplen was built by a single operator who had the first and not the second. Every line of implementation was produced by Claude through conversational interface. Every architectural decision — which database, which authentication model, which generation pipeline, how to structure the curriculum hierarchy — was made by the operator.

The result:

| Metric | Value |
|---|---|
| Calendar days to production | 32 |
| Total tooling cost | USD 500 |
| Documented modules | 34 |
| Operator-model conversation turns | 3,662 |
| Estimated traditional equivalent cost | USD 150,000–280,000 |
| Cost compression ratio | ~300× |
| System uptime (production period) | 99.7% |

This is not a prototype. The system processed 200 curriculum textbooks across 3 grade levels, 18 subjects, 108 topics, and 432 subtopics. The first video produced using a Kaplen-generated script achieved 60% average view duration and 7% click-through rate on YouTube — above the 2–3% CTR platform average and above the 50% AVD threshold considered strong for educational content.

### The Four Failure Modes — and Why They Matter to Users

The research paper identified four failure modes that appear when an LLM is used as a sole implementation agent. These are worth knowing because they shaped Kaplen's architecture in ways that make the platform more reliable than it would otherwise be.

**Configuration Blindness** — the model cannot observe runtime environment state. It produces code that is syntactically correct but fails because it assumes an environment that doesn't exist (a file at a path, an API key in memory, a database already running). The operator's compensating behavior: explicit environment diagnosis before any debugging session begins.

**Fragmentation** — the model loses architectural coherence across long sessions, producing code that contradicts earlier decisions. Function signatures stop matching their call sites. Database schemas diverge from code. The compensating behavior: context pre-loading — re-establishing full system state at the start of every session, the manual equivalent of what is now formalized as AGENTS.md.

**Accumulation Without Consolidation** — the model adds complexity without detecting when complexity has exceeded manageability. The orchestrator file grew from 9KB to 74KB across 81 snapshots before the operator intervened and reduced it to 4KB. None of the consolidation was model-initiated. The compensating behavior: explicit consolidation instructions when complexity crossed a threshold.

**Scope Creep** — the model expands output beyond what was requested. A request to fix a script generation bug produced 10+ documentation files, deployment checklists, and visual summaries. The compensating behavior: phase-gate prompting — dividing sessions into explicit phases with required model acknowledgment before proceeding.

These compensating behaviors are now standard operating procedure in the platform's ongoing development. They appear in the SPEC.md, the ARCHITECTURE.md, and in every production session.

---

## Part II — The Education Platform

### The Problem It Solves

Iraqi schoolteachers face a specific constraint: the Ministry of Education curriculum is mandatory, standardized, and dense. Teachers who want to produce supplementary YouTube content — to reach students outside the classroom, to make topics more engaging, to build a channel that supports their income — must translate that curriculum into spoken, watchable content. That translation is hard. It requires knowing what to cut, how to structure a 10-minute explanation, how to write for an ear rather than an eye.

Kaplen automates that translation.

### What the Platform Does

A teacher uploads a curriculum PDF or selects a pre-loaded textbook. The platform classifies the content into a subject → topic → subtopic hierarchy aligned to the Iraqi MoE structure. The teacher selects a subtopic. The generation pipeline produces:

- A full Arabic-language YouTube script, structured for the selected video duration
- A thumbnail concept with title, subtitle, and visual description
- Callaway beats — the rhythmic emphasis points that keep viewers watching
- A YouTube-ready package: title, description, tags, timestamps

The script is not a summary of the textbook. It is written for spoken delivery: contractions, direct address, natural transitions, a hook strong enough to earn the first 30 seconds of a viewer's attention.

### Curriculum Coverage

| Dimension | Scale |
|---|---|
| Textbooks processed | 200 |
| Grade levels | 3 |
| Subjects | 18 |
| Topics | 108 |
| Subtopics | 432 |

The curriculum registry is extensible. New textbooks are ingested via the `/api/curriculum/upload` endpoint, classified automatically, and available for script generation within minutes.

### Business Model

The platform is sold to educational centers — organizations that employ 7–20 teachers. This center-level billing model was a deliberate architectural choice: it concentrates the subscription decision at the center director level, where budget authority exists, rather than requiring individual teacher subscriptions.

Unit economics validated in the production period:

- **Per-teacher cost**: USD 67/month
- **Per-center price point**: USD 469–1,340/month (depending on center size)
- **Customer stage reached before research pause**: letter-of-intent

### Performance Signal

The first video produced using a Kaplen-generated script, thumbnail, and title:

- **Average View Duration**: 60% — above the 50% threshold considered strong for educational content
- **Click-Through Rate**: 7% — 3.5× the platform average of 2–3%

This is a single data point, not a controlled study. But it establishes that the generation pipeline produces content that YouTube viewers complete and click on — which is the minimum bar for the product to be useful.

---

## Part III — The Script Studio

### Beyond the Classroom

The same generation architecture that converts curriculum PDFs into teacher scripts can convert *any* written material into video-ready spoken content. This is the Script Studio.

The use cases are immediate:

- A **journalist** who covers a beat and writes long-form pieces wants to repurpose that research as a YouTube explainer without rebuilding the argument from scratch
- A **researcher** who publishes papers wants a 15-minute video that makes the work accessible without dumbing it down
- A **writer** who produces essays or commentary wants to adapt their voice — which reads well on a page — into a voice that works on camera
- A **commentator** who has opinions but no production workflow wants a structured script that goes from hook to evidence to call to action in a format a solo creator can execute

What all of these share: they already have the research. They already have the argument. What they need is the *format conversion* — from written to spoken, from essay structure to video structure, from page rhythm to screen rhythm.

### The Format Problem

Written and spoken content are structurally different in ways that matter for viewer retention.

Written content can be re-read. A complex sentence that requires two passes is a nuisance on the page and an abandonment event on YouTube. Written content uses formal connectors ("furthermore," "in contrast," "it is worth noting that"). Spoken content uses natural transitions ("So here's the thing —", "But wait —", "Now, this is where it gets interesting"). Written content assumes a reader who chose to engage with the full argument. Spoken content must re-earn attention at every scene cut.

The Script Studio's generation pipeline enforces these constraints explicitly. The spoken-word prompt rules:

```
STRICT RULES:
- SPOKEN WORD only: use contractions ("it's", "don't"), direct address ("you", "we")
- Natural transitions ("So...", "Now here's the thing...", "But wait —")
- No academic language, no formal essay structure
- If this is the Hook: start with strongest possible opening line
- If this is the Outro: end with CTA (like, subscribe, link in description)
```

These are not style suggestions. They are enforced constraints on every section of every generated script.

### Script Structure

Scripts are generated in timed sections. Each section has a name, a start time, an end time, a target word count, key points to cover, and production instructions. A 15-minute script looks like:

| Section | Time | Words | Function |
|---|---|---|---|
| Hook | 0:00–0:45 | ~120 | Strongest opening line. Earn the first minute. |
| Context | 0:45–3:00 | ~350 | Why this matters. Stakes. |
| Main Point 1 | 3:00–6:00 | ~500 | First major argument. Evidence. |
| Main Point 2 | 6:00–9:00 | ~500 | Second argument. Pivot. |
| Main Point 3 | 9:00–12:00 | ~500 | Third argument. Build. |
| Synthesis | 12:00–14:00 | ~320 | Connect the arguments. |
| Outro + CTA | 14:00–15:00 | ~160 | What to do next. Subscribe prompt. |

The operator specifies duration (10, 15, or 25 minutes), style (Explainer / Commentary / Analysis / Personal Take), and target audience. The pipeline handles the sectioning, timing, and spoken-word formatting.

### The Long-Form Mode

For operators who need extended written content rather than video scripts, the same pipeline produces long-form essays: 5,000-word short-form pieces, 12,000-word medium pieces, or 30,000-word long-form documents. These follow academic or editorial structure rather than video structure, with formal argumentation, evidence integration, and citation-ready sourcing.

Both modes — YouTube Script and Long-Form Essay — are available in a single interface. The operator selects the output format; the generation pipeline routes accordingly.

---

## Part IV — The Technical Foundation

### Architecture

Kaplen is a multi-tenant B2B SaaS platform. The stack:

- **Backend**: Python / Flask API, 34 documented modules
- **Database**: PostgreSQL on AWS RDS — 12 tables, 45 API endpoints
- **Storage**: AWS S3 for curriculum PDFs and generated artifacts
- **LLM**: Provider-agnostic — Anthropic Claude (primary), with interfaces for OpenAI, Ollama, Together AI, Groq
- **Infrastructure**: AWS EC2 (t3.small), Nginx reverse proxy, JWT authentication
- **Payments**: Stripe integration
- **Frontend**: Single-page web dashboard

The provider-agnostic design is a direct consequence of the operator's architectural judgment during the build. Locking the system to a single LLM provider was identified as a fragility risk early. The `LLMProvider` abstraction — with `complete()` and `stream_complete(on_token=)` as its two required methods — was specified by the operator and implemented by Claude.

### The Generation Pipeline

Content generation uses Server-Sent Events (SSE) for real-time streaming. Long-form generation is chunked into sections — each section generated independently, assembled sequentially — to avoid context-window limitations on 30,000-word documents.

The pipeline for a YouTube script:

```
Input (topic + style + duration)
    → Outline generation (timed sections, key points per section)
    → Parallel section generation (spoken-word constraints, chunked)
    → Script assembly (timing markers, section headers)
    → YouTube packaging (title, description, tags, timestamps)
    → SSE stream to client
```

The deduplication layer (Dual-Hash approach) prevents regenerating content for subtopics that have already been processed. The batch processing system handles bulk curriculum ingestion without blocking the API.

### The 34 Modules

The final system comprises 34 documented modules across five categories:

| Category | Modules |
|---|---|
| Core Generation Pipeline | essay_generator, long_form_generator, script_generator, study_tips, dedup |
| Data and Architecture | database, data_model, data_loader, synthesis |
| Infrastructure and Deployment | deployment, health, security, auth, api_endpoints |
| Analytics and Metrics | analytics, metrics, dashboard, batch |
| Feature Extensions | callaway, validator, youtube_packager, payments, timeline |

Full API documentation — all 45 endpoints with request/response schemas — is in `SPEC.md`. Architecture diagrams and module descriptions are in `ARCHITECTURE.md`. Deployment guides for local, Docker, Heroku, and EC2 are in `DEPLOYMENT.md`.

---

## Part V — The Build Process as Methodology

The research paper documents not just what was built but how. That how is reproducible. The operator developed four compensating behaviors across 18 sessions — behaviors that represent an informal but functional methodology for operator-directed LLM development.

### The Protocol

**Session initialization** — before any implementation request, provide the model with a structured system description: stack, purpose, active modules, constraints established in prior sessions. This compensates for the model's lack of persistent memory. The initialization prompt format: *"Here is the current system state before we begin."*

**Phase-gate prompting** — divide each session into explicit phases. Require model acknowledgment before proceeding to the next phase. The gate prevents scope creep by creating a confirmation checkpoint. The specific protocol used in this build: *"Say 'next' and I'll move to PART 2."*

**Complexity monitoring** — track a proxy metric for system complexity (file sizes, module count, line count). When any proxy metric grows beyond a threshold set in advance, schedule a consolidation session before adding new features. The orchestrator file's growth from 9KB to 74KB was recognized retrospectively as too late; a threshold of 30–40KB would have triggered earlier intervention.

**Failure mode triage** — when a session produces unexpected failures, classify the failure before debugging. The four failure modes map to distinct diagnostic paths:
- Configuration blindness → environment inspection, not code review
- Fragmentation → architectural comparison against known-good state
- Accumulation → consolidation, not new implementation
- Scope creep → constraint injection, not elaboration

Applying the wrong diagnostic path wastes turns. The operator learned this empirically across 3,662 turns and encoded it as standard practice.

### What This Means for Future Builds

The paper's conclusion is careful: this is a single-subject study (N=1). The findings are not statistically generalizable. The operator's CS background may be a confounding variable — the compensating behaviors required to manage the four failure modes draw on knowledge typically acquired through engineering training: recognizing configuration-layer failures, maintaining architectural coherence across sessions, knowing when to rebuild rather than patch.

What the study does establish: one engineering-trained operator successfully delivered a production system without coding. The failure modes and compensating behaviors documented here are not idiosyncratic — they are recognized in the broader LLM failure mode literature (Cemri et al., 2025) and have since been addressed by emerging standards (AGENTS.md, July 2025). The methodology is real. The protocol is reproducible.

---

## Part VI — What Kaplen Is, Precisely

Kaplen is three things at once:

**An education platform** — that converts Iraqi Ministry of Education curriculum materials into Arabic-language YouTube scripts, thumbnails, and video packages, sold to educational centers at $469–1,340/month, with validated performance above YouTube platform averages.

**A content creation platform** — that converts any written material (articles, research, essays, commentary) into spoken-word YouTube scripts with timed sections, enforced spoken-word constraints, and production-ready structure for creators who want to reach video audiences without abandoning their research workflows.

**A case study in operator-driven AI development** — that demonstrates, at production scale, that software engineering competence and coding ability function as separable skills when an LLM is used as the implementation agent. Built in 32 days at USD 500. 34 modules. 3,662 documented operator-model turns. 99.7% uptime.

These three things are not independent. The education platform is what Kaplen does for teachers. The content creation platform is what Kaplen does for writers. The research case study is what Kaplen *is* — a documented proof that the platform could be built the way it was built, and that the way it was built produces something that works.

---

## Repository Structure

```
KaplenOpen/
├── README.md          — Quick start, provider switching, API overview
├── ARCHITECTURE.md    — Layer diagram, all 34 modules, pipeline flows, DB schema
├── DEPLOYMENT.md      — Local, Docker, Heroku, EC2 — full environment variable reference
├── SPEC.md            — All 45 endpoints, all 12 DB tables, LLM interface, SSE protocol
└── OVERVIEW.md        — This document
```

The live system is accessible at **kaplen.app**.

The research paper — *"Engineering Without Coding: A Practitioner Study of Operator-Driven AI Development"* (Azeez, 2026) — is available as a separate document. The raw conversation corpus, module documentation, and rule-based classifier source code are available as ancillary files to that paper.

---

*MohamadAlmstafa Azeez — Independent Researcher, Baghdad, Iraq*
