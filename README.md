# NOC Triage Agent v2 — AI-Powered Digital Twin

> **Live Demo:** [noc-agent-v2.vercel.app](https://noc-agent-v2.vercel.app) — no login required  
> **Phase 1 Repo:** [noc-triage-agent](https://github.com/hassan-aiml/noc-triage-agent)

---

## What this is

A live network digital twin that visualizes DAS (Distributed Antenna System) topology in real time and feeds spatial fault context to an AI triage agent — so it sees the **shape of the problem** before it reasons about it.

Phase 1 gave the agent a brain (RAG over 21 runbooks + Claude reasoning → structured triage brief).  
Phase 2 gives it eyes (live topology rendering + fault propagation + correlation engine).

When an alarm fires, the system:
1. Maps the fault across the topology — root cause node, downstream blast radius
2. Renders the live state: healthy (green), root fault (red), impacted (amber)
3. Retrieves relevant runbook context via vector search (Voyage AI + Supabase pgvector)
4. Calls Claude with alarm data + topology context + runbook chunks
5. Outputs a structured triage brief: incident ID, severity (P1–P5), root cause, affected nodes, diagnostic checklist, dispatch recommendation, sparing note

---

## Demo scenarios

| Scenario | Description | Key insight |
|---|---|---|
| **Single RU Failure** | RU-01 VSWR High — isolated radio head fault | P3 · internal · DAS vendor dispatch |
| **Food Court Hub Failure** | EH-01 fiber LOS — all 5 downstream RUs offline | Correlation engine identifies hub as root cause, not 5 individual RUs |
| **Meridian n41 Signal Loss** | DL power low across all n41 RUs | Traces to POI-MDN-N41 — carrier issue, do not dispatch |

The hub failure scenario is the most important one: without topology context, an engineer might open 5 tickets and dispatch to the DAS vendor. With it, the correlation engine sees the blast radius pattern and correctly classifies it as a single hub fault — notify carrier, check fiber, do not dispatch.

---

## Architecture

```
Browser (React + ReactFlow)
    ↓  POST /simulate { scenario }
FastAPI (Railway)
    ├── CorrelationEngine   → maps fault nodes + impacted nodes
    ├── TopologyManager     → builds incident object (severity, scope, affected)
    └── TriageLogic
            ├── Voyage AI   → embeds alarm description
            ├── Supabase    → pgvector similarity search → top 5 runbook chunks
            └── Anthropic Claude → structured triage brief
    ↓  JSON response
React state update → FlowContainer re-renders topology → TriageTerminal streams brief
```

---

## Tech stack

**Frontend**
- React 18 · ReactFlow · JetBrains Mono · Vercel

**Backend**
- FastAPI · Python 3.14 · Pydantic · Uvicorn · Railway

**AI / Data**
- Anthropic Claude (claude-sonnet-4-5) · Voyage AI embeddings · Supabase pgvector · LangChain

---

## Demo assumptions vs. production

This is a demonstration of the AI reasoning and topology visualization pattern. Production would require:

| Demo | Production |
|---|---|
| Single-zone venue | Multi-zone, multi-sector topology |
| Fictitious carrier names | Band 66, n41, AWS · SOLiD, JMA, CommScope |
| Canonical alarm names | Native OEM alarm strings + normalization layer |
| No persistent state | Live health state DB with existing faults |
| No alarm aggregation | Correlation window (hub failure → 1 P1, not 5 P2s) |

These aren't gaps — they're Phase 3 engineering targets.

---

## Run locally

**Backend**
```bash
cd backend
pip install -r requirements.txt

# Create backend/.env
ANTHROPIC_API_KEY=your_key
VOYAGE_API_KEY=your_key
SUPABASE_URL=your_url
SUPABASE_SERVICE_KEY=your_key

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend**
```bash
cd frontend
npm install

# Create frontend/.env.local
REACT_APP_API_URL=http://localhost:8000

npm start
# Opens at http://localhost:3000
```

---

## What's next — Phase 3

Phase 3 makes this truly agentic using LangGraph:

```
Detect → Correlate → Reason → Propose → Human Approves → Act → Monitor → repeat
```

- Autonomous alarm ingestion (no human trigger)
- Multi-agent reasoning loop
- Slack / email delivery
- Human-in-the-loop approval gates
- RAGAS eval pipeline for brief quality scoring
- Docker · GitHub Actions CI/CD

The NOC engineer stops being the first responder. They become the approver.

---

## Related

- **Phase 1:** [noc-triage-agent](https://github.com/hassan-aiml/noc-triage-agent) — RAG pipeline, runbook knowledge base, alarm classification
- **LinkedIn article:** [I gave my NOC triage agent a pair of eyes](https://linkedin.com/in/hassan73)

---

*Built by [Hassan M. Hai](https://linkedin.com/in/hassan73) — DAS Engineering Leader & AI Builder · 20 years wireless infrastructure*

#AgenticAI #DigitalTwin #RAG #Claude #ReactFlow #LangChain #NetworkOperations
