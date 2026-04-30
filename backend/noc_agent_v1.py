"""
NOC Triage Agent — Walking Skeleton
=====================================
This is your first working build. No LangGraph, no orchestrator,
no multi-agent framework. Just:

  1. An alarm comes in (hardcoded for now)
  2. KB is queried via Supabase pgvector
  3. Claude reasons over the retrieved context
  4. Classification + recommendation printed

Goal for Saturday: get this running end-to-end on ONE alarm.
That's it. Don't add features. Get the loop working first.

Run:
    python noc_agent_v1.py
    python noc_agent_v1.py --alarm INT-010   # try a different alarm
    python noc_agent_v1.py --alarm EXT-001   # external alarm test
"""

import os
import json
import argparse
from dotenv import load_dotenv
import anthropic
from supabase import create_client

load_dotenv()

# ── Clients ──────────────────────────────────────────────────────────
ac = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# ── Demo alarm library ────────────────────────────────────────────────
# These simulate what would come from a real NMS alarm feed.
# In Phase 2 you'll replace this with a live CSV reader or API.
DEMO_ALARMS = {
    "INT-006": {
        "alarm_id":    "INT-006",
        "site":        "Grand Hyatt Dallas — Floor 12",
        "remote_id":   "RU-04",
        "timestamp":   "2025-01-15 02:47:33",
        "description": "Downlink output power low on single remote RU-04. Measured -18 dBm, threshold -12 dBm. All other remotes under same hub showing normal DL output. No EXT-001 active on any POI.",
        "raw_snmp":    "DL_OUTPUT_POWER_LOW · site=GRAND_HYATT_F12 · remote=RU-04 · measured=-18dBm · other_remotes=normal · poi_alarms=none",
    },
    "INT-006-POI": {
        "alarm_id":    "INT-006",
        "site":        "Northpark Center Mall — Food Court",
        "remote_id":   "RU-01, RU-02, RU-03, RU-04, RU-05",
        "timestamp":   "2025-01-15 03:55:12",
        "description": "Downlink output power low on ALL 5 remotes under HUB-01 simultaneously. Measured -22 dBm across all units, threshold -12 dBm. All carriers and all bands affected. Pattern is consistent with POI input loss upstream rather than individual remote hardware faults.",
        "raw_snmp":    "DL_OUTPUT_POWER_LOW · site=NORTHPARK_FOOD_COURT · remotes=RU-01,RU-02,RU-03,RU-04,RU-05 · all_measured=-22dBm · hub=HUB-01 · all_carriers_affected=true · all_bands_affected=true",
    },
    "INT-010": {
        "alarm_id":    "INT-010",
        "site":        "Union Station Dallas — Main Concourse",
        "remote_id":   "HUB-01-MAIN",
        "timestamp":   "2025-01-15 03:12:05",
        "description": "TDD clock sync lost at main hub. GPS reference no longer locked. Affects Meridian Mobile n41 (5G TDD) band only. FDD bands B2, B4, B13 for all carriers are unaffected. GPS antenna located on rooftop above equipment room.",
        "raw_snmp":    "TDD_SYNC_LOST · site=UNION_STATION_MAIN · hub=HUB-01-MAIN · poi=POI-MDN-N41 · band=n41 · carrier=Meridian · fdd_bands=normal · gps_status=unlocked",
    },
    "INT-002": {
        "alarm_id":    "INT-002",
        "site":        "One Uptown Tower — All Floors",
        "remote_id":   "HUB-01-MAIN",
        "timestamp":   "2025-01-15 04:05:18",
        "description": "Main hub HUB-01-MAIN unreachable on management network. All 14 remotes offline. Expansion hub HUB-02-EXP also unreachable — downstream of main hub. All carriers and all bands are down across the entire sector. When the main hub is offline nothing downstream is reachable, including expansion hubs and remotes.",
        "raw_snmp":    "HUB_OFFLINE · site=ONE_UPTOWN_TOWER · hub=HUB-01-MAIN · remotes_affected=14 · expansion_hub=HUB-02-EXP · expansion_hub_status=unreachable · all_carriers_down=true · all_bands_down=true · mgmt_ping=failed",
    },
    "EXT-001": {
        "alarm_id":    "EXT-001",
        "site":        "Northpark Center Mall — Food Court",
        "remote_id":   "POI-MDN-N41",
        "timestamp":   "2025-01-15 05:33:41",
        "description": "DL input power low at POI-MDN-N41. Meridian Mobile n41 (5G TDD) signal absent at POI. Measured -41 dBm, expected -10 to -15 dBm. Meridian n41 service is down across the entire sector — main hub, expansion hub, and all remotes. All other POIs for other carriers and bands are showing normal input levels. This is carrier-specific and band-specific.",
        "raw_snmp":    "DL_INPUT_LOSS · site=NORTHPARK_FOOD_COURT · poi=POI-MDN-N41 · carrier=Meridian · band=n41 · measured=-41dBm · sector_impact=full · other_pois=normal · other_carriers=normal",
    },
    "INT-005": {
        "alarm_id":    "INT-005",
        "site":        "DFW Terminal B — Gates B1-B20",
        "remote_id":   "RU-11",
        "timestamp":   "2025-01-15 06:18:22",
        "description": "Overtemperature alarm on remote unit RU-11. Current temp 68C, operational threshold 60C, auto-shutdown threshold 75C. Fan fault also active on same unit. Equipment room HVAC reported normal by facilities. Risk of auto-shutdown if not resolved.",
        "raw_snmp":    "OVERTEMP · site=DFW_TERMINAL_B · remote=RU-11 · temp=68C · op_threshold=60C · shutdown_threshold=75C · fan_fault=TRUE · hvac=normal",
    },
}


# ── Step 1: Embed the alarm for retrieval ─────────────────────────────
def embed_alarm(alarm: dict) -> list[float]:
    """
    Turn the alarm into a vector for similarity search.
    We embed the description + alarm ID so retrieval matches
    on both the fault type and the natural language description.
    """
    import voyageai
    query_text = f"Alarm {alarm['alarm_id']}: {alarm['description']}"
    print(f"  Embedding: '{query_text[:80]}...'")
    vo = voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY", ""))
    result = vo.embed([query_text], model="voyage-3", input_type="query")
    return result.embeddings[0]


# ── Step 2: Retrieve relevant runbook chunks from Supabase ────────────
def retrieve_context(embedding: list[float], alarm_id: str, top_k: int = 5) -> list[dict]:
    """
    Query Supabase pgvector for the most relevant runbook chunks.

    We use two passes:
    1. Exact alarm ID match first — always include the primary runbook
    2. Semantic similarity for related context (e.g. EXT-001 when INT-006 fires)
    """
    # Pass 1: exact alarm ID lookup (get the direct runbook regardless of similarity)
    exact = sb.table("noc_kb_chunks") \
              .select("alarm_id, category, severity, alarm_name, section, content") \
              .eq("alarm_id", alarm_id) \
              .limit(3) \
              .execute()

    # Pass 2: semantic similarity search across full KB
    semantic = sb.rpc("match_noc_chunks", {
        "query_embedding": embedding,
        "match_count": top_k,
        "filter_category": None,
        "filter_severity": None,
    }).execute()

    # Merge, deduplicate by content
    seen = set()
    chunks = []
    for row in (exact.data or []) + (semantic.data or []):
        key = row.get("content", "")[:100]
        if key not in seen:
            seen.add(key)
            chunks.append(row)

    print(f"  Retrieved {len(chunks)} chunks ({len(exact.data or [])} exact + semantic)")
    return chunks[:8]  # cap at 8 to stay within context budget


# ── Step 3: Format context for the prompt ────────────────────────────
def format_context(chunks: list[dict]) -> str:
    """Package retrieved chunks into a readable block for Claude."""
    lines = []
    for i, c in enumerate(chunks, 1):
        lines.append(
            f"[RUNBOOK {i}] {c.get('alarm_id','?')} — {c.get('alarm_name','?')} "
            f"| Section: {c.get('section','?')}\n{c.get('content','')}"
        )
    return "\n\n---\n\n".join(lines)


# ── Step 4: Run the triage agent ──────────────────────────────────────
def run_triage(alarm: dict, context: str) -> dict:
    """
    Send alarm + retrieved context to Claude.
    Returns structured triage result as a dict.
    """

    system_prompt = """You are a DAS (Distributed Antenna System) NOC triage agent for a third-party operator (3PO).

Your job is to analyze incoming alarms and produce a structured triage brief for the Operations team.

You have access to a knowledge base of DAS runbooks. Use the retrieved context to reason accurately.

CRITICAL RULES:
1. Always determine if the alarm is INTERNAL (DAS hardware — our problem) or EXTERNAL (carrier BTS/RAN signal — notify carrier, do not dispatch vendor).
2. For INT-006 (DL output power low): ALWAYS check if EXT-001 (DL input at POI) is also active before classifying as internal. This is the most common misdiagnosis.
3. For TDD sync alarms: always P1 or P2, never lower. Recommend disabling TDD carriers if sync is lost.
4. Never recommend auto-dispatch. Always recommend human review.
5. Be specific — reference runbook IDs, alarm IDs, and exact steps from the retrieved context.

Respond ONLY with a valid JSON object. No markdown, no preamble. Exactly this structure:
{
  "classification": "INTERNAL" or "EXTERNAL",
  "severity": "P1" or "P2" or "P3",
  "alarm_name": "human readable alarm name",
  "probable_causes": ["most likely cause", "second most likely", "third if relevant"],
  "immediate_action": "what NOC should do RIGHT NOW in one sentence",
  "notify_carrier": true or false,
  "carrier_to_notify": "carrier name or null",
  "dispatch_vendor": "DO NOT DISPATCH" or "OPERATIONS REVIEW REQUIRED",
  "diagnostic_checklist": ["step 1", "step 2", "step 3"],
  "vendor_kit": ["material 1", "material 2"] or [],
  "reasoning": "2-3 sentences explaining why you classified it this way",
  "servicenow_queue": "NOC-Internal-DAS" or "NOC-External-Carrier"
}"""

    user_prompt = f"""INCOMING ALARM:
Site: {alarm['site']}
Remote/Hub: {alarm['remote_id']}
Alarm ID: {alarm['alarm_id']}
Timestamp: {alarm['timestamp']}
Description: {alarm['description']}
Raw SNMP: {alarm['raw_snmp']}

RETRIEVED RUNBOOK CONTEXT:
{context}

Analyze this alarm and return the structured triage JSON."""

    response = ac.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if Claude adds them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


# ── Step 5: Print the triage brief ───────────────────────────────────
def print_brief(alarm: dict, result: dict):
    """Format and print the escalation brief to console."""
    SEV_COLOR = {"P1": "\033[91m", "P2": "\033[93m", "P3": "\033[94m"}
    CLS_COLOR = {"INTERNAL": "\033[96m", "EXTERNAL": "\033[95m"}
    RESET     = "\033[0m"
    BOLD      = "\033[1m"
    GREEN     = "\033[92m"
    DIM       = "\033[2m"

    sev = result.get("severity", "P2")
    cls = result.get("classification", "INTERNAL")
    sev_c = SEV_COLOR.get(sev, "")
    cls_c = CLS_COLOR.get(cls, "")

    print(f"\n{'='*65}")
    print(f"{BOLD}  NOC TRIAGE BRIEF{RESET}")
    print(f"{'='*65}")
    print(f"  Site:       {alarm['site']}")
    print(f"  Alarm:      {BOLD}{alarm['alarm_id']}{RESET} — {result.get('alarm_name','')}")
    print(f"  Time:       {alarm['timestamp']}")
    print(f"  Severity:   {sev_c}{BOLD}{sev}{RESET}")
    print(f"  Type:       {cls_c}{BOLD}{cls}{RESET}")
    print(f"  SN Queue:   {result.get('servicenow_queue','')}")
    print(f"{'─'*65}")

    print(f"\n  {BOLD}IMMEDIATE ACTION{RESET}")
    print(f"  {result.get('immediate_action','')}")

    if result.get("notify_carrier"):
        print(f"\n  {BOLD}CARRIER NOTIFICATION REQUIRED{RESET}")
        print(f"  Notify: {result.get('carrier_to_notify','')}")
        print(f"  Ref: OPS-001 carrier notification procedure")

    print(f"\n  {BOLD}PROBABLE CAUSES{RESET}")
    for i, cause in enumerate(result.get("probable_causes", []), 1):
        print(f"  {i}. {cause}")

    print(f"\n  {BOLD}DIAGNOSTIC CHECKLIST{RESET}")
    for i, step in enumerate(result.get("diagnostic_checklist", []), 1):
        print(f"  {i}. {step}")

    vendor_kit = result.get("vendor_kit", [])
    if vendor_kit:
        print(f"\n  {BOLD}VENDOR FIRST-TRIP KIT{RESET}")
        for item in vendor_kit:
            print(f"  · {item}")

    print(f"\n  {BOLD}DISPATCH RECOMMENDATION{RESET}")
    print(f"  {result.get('dispatch_vendor','')}")

    print(f"\n  {DIM}AGENT REASONING{RESET}")
    print(f"  {DIM}{result.get('reasoning','')}{RESET}")

    print(f"\n{'='*65}\n")


# ── Main ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="NOC Triage Agent v1 — Walking Skeleton")
    parser.add_argument(
        "--alarm",
        default="INT-006",
        choices=list(DEMO_ALARMS.keys()),
        help="Alarm ID to triage (default: INT-006 — the misdiagnosis demo)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all demo alarms sequentially"
    )
    args = parser.parse_args()

    alarms_to_run = list(DEMO_ALARMS.values()) if args.all else [DEMO_ALARMS[args.alarm]]

    for alarm in alarms_to_run:
        print(f"\n{'─'*65}")
        print(f"Processing alarm: {alarm['alarm_id']} — {alarm['site']}")
        print(f"{'─'*65}")

        print("\n[1/4] Embedding alarm...")
        embedding = embed_alarm(alarm)

        print("\n[2/4] Retrieving runbook context...")
        chunks = retrieve_context(embedding, alarm["alarm_id"])

        print("\n[3/4] Running triage agent...")
        context = format_context(chunks)
        result = run_triage(alarm, context)

        print("\n[4/4] Triage complete.")
        print_brief(alarm, result)

        # Save the result as JSON for LangSmith / logging later
        outfile = f"triage_{alarm['alarm_id']}_{alarm['timestamp'].replace(' ','_').replace(':','-')}.json"
        with open(outfile, "w") as f:
            json.dump({"alarm": alarm, "result": result}, f, indent=2)
        print(f"  Saved: {outfile}")

        if args.all and alarm != alarms_to_run[-1]:
            print("\n  [Press Enter to run next alarm, or Ctrl+C to stop]")
            input()


if __name__ == "__main__":
    main()
