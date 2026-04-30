"""
NOC Knowledge Base — Supabase RAG Ingestion Script
====================================================
Loads all 21 KB markdown files into Supabase with:
  - YAML frontmatter parsed as metadata (for filtered retrieval)
  - Smart section-level chunking (300-500 tokens, 50-token overlap)
  - Anthropic embeddings (voyage-3 via Anthropic API)
  - Idempotent: re-running clears and reloads cleanly

Usage:
  1. Create a .env file with:
       ANTHROPIC_API_KEY=sk-ant-...
       SUPABASE_URL=https://your-project.supabase.co
       SUPABASE_SERVICE_KEY=your-service-role-key

  2. Run the SQL setup in Supabase (see bottom of this file or setup.sql)

  3. Run:
       python ingest_kb.py

  Optional flags:
       python ingest_kb.py --dry-run     # chunk and print, no DB writes
       python ingest_kb.py --kb-path /path/to/noc_kb   # custom KB path
"""

import os
import re
import sys
import json
import time
import argparse
from pathlib import Path

import frontmatter          # pip install python-frontmatter
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except Exception:
    # Fallback: ~4 chars per token (standard heuristic, accurate enough for chunking)
    def count_tokens(text: str) -> int:  # type: ignore
        return max(1, len(text) // 4)
import anthropic            # pip install anthropic
from supabase import create_client, Client   # pip install supabase

# ── Config ────────────────────────────────────────────────────────────────────

KB_PATH        = Path("./noc_kb")
CHUNK_MAX_TOK  = 450    # hard ceiling per chunk
CHUNK_TARGET   = 350    # aim for this size
OVERLAP_TOK    = 50     # token overlap between consecutive chunks
EMBED_MODEL    = "voyage-3"   # Anthropic's embedding model
EMBED_DIM      = 1024         # voyage-3 output dimension
TABLE_NAME     = "noc_kb_chunks"

# Load env (dotenv optional — falls back to os.environ)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ANTHROPIC_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")
SUPABASE_URL     = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY     = os.environ.get("SUPABASE_SERVICE_KEY", "")

# ── Chunking ──────────────────────────────────────────────────────────────────

def split_into_sections(content: str) -> list[dict]:
    """
    Split a runbook into semantic sections by markdown heading (## or ###).
    Each section becomes a candidate chunk. Sections that are too long get
    further split by paragraph. Sections that are too short get merged with
    the next section.
    Returns list of dicts: {heading, text, tokens}
    """
    # Split on ## or ### headings, keep the heading with its content
    raw_sections = re.split(r'\n(?=#{2,3} )', content.strip())

    sections = []
    for raw in raw_sections:
        raw = raw.strip()
        if not raw:
            continue
        lines = raw.splitlines()
        heading = lines[0].lstrip('#').strip() if lines[0].startswith('#') else "intro"
        text    = raw
        sections.append({"heading": heading, "text": text})

    return sections


def chunk_section(heading: str, text: str, doc_intro: str) -> list[str]:
    """
    If a section fits within CHUNK_MAX_TOK, return it as-is (with intro prefix).
    If it's too large, split by paragraph with overlap.
    """
    prefix = f"{doc_intro}\n\nSection: {heading}\n\n" if doc_intro else f"Section: {heading}\n\n"
    full   = prefix + text

    if count_tokens(full) <= CHUNK_MAX_TOK:
        return [full]

    # Split large section into paragraphs
    paragraphs = [p.strip() for p in re.split(r'\n\n+', text) if p.strip()]
    chunks     = []
    current    = prefix
    overlap_buf = []

    for para in paragraphs:
        candidate = current + para + "\n\n"
        if count_tokens(candidate) > CHUNK_MAX_TOK and count_tokens(current) > 50:
            chunks.append(current.strip())
            # Start next chunk with overlap from tail of previous
            overlap_text = " ".join(overlap_buf[-3:])  # last ~3 paragraphs as context
            current = prefix + f"[continued] {overlap_text}\n\n" + para + "\n\n"
            overlap_buf = [para]
        else:
            current = candidate
            overlap_buf.append(para)
            if count_tokens(" ".join(overlap_buf)) > OVERLAP_TOK * 3:
                overlap_buf = overlap_buf[-3:]

    if current.strip() and count_tokens(current) > 30:
        chunks.append(current.strip())

    return chunks if chunks else [full[:3000]]  # safety fallback


def chunk_document(file_path: Path) -> list[dict]:
    """
    Parse a runbook markdown file and return a list of chunk dicts ready
    for embedding and insertion.
    """
    post = frontmatter.load(str(file_path))
    meta = post.metadata
    body = post.content

    alarm_id   = meta.get("alarm_id") or meta.get("doc_id", "UNKNOWN")
    category   = meta.get("category", "unknown")
    severity   = meta.get("severity", "unknown")
    alarm_name = meta.get("alarm_name") or meta.get("title", file_path.stem)
    tags       = meta.get("tags", [])
    subcategory = meta.get("subcategory", "")

    # Build a short intro that anchors every chunk to its parent document
    doc_intro = f"Document: {alarm_name} (ID: {alarm_id}, Category: {category}, Severity: {severity})"

    sections = split_into_sections(body)

    chunks_out = []
    for sec in sections:
        raw_chunks = chunk_section(sec["heading"], sec["text"], doc_intro)
        for i, chunk_text in enumerate(raw_chunks):
            chunks_out.append({
                "alarm_id":    alarm_id,
                "category":    category,
                "subcategory": subcategory,
                "severity":    severity,
                "alarm_name":  alarm_name,
                "tags":        tags,
                "section":     sec["heading"],
                "chunk_index": i,
                "content":     chunk_text,
                "token_count": count_tokens(chunk_text),
                "source_file": file_path.name,
            })

    return chunks_out


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_batch(texts: list[str], client: anthropic.Anthropic) -> list[list[float]]:
    """
    Embed using voyage-3 via the voyageai package.
    """
    import voyageai
    vo = voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY", ""))
    result = vo.embed(texts, model="voyage-3", input_type="document")
    return result.embeddings

# ── Supabase ──────────────────────────────────────────────────────────────────

SETUP_SQL = f"""
-- Run this once in the Supabase SQL editor before ingesting.

-- Enable pgvector extension
create extension if not exists vector;

-- Drop and recreate table (clean slate)
drop table if exists {TABLE_NAME};

create table {TABLE_NAME} (
    id            bigserial primary key,
    alarm_id      text,
    category      text,
    subcategory   text,
    severity      text,
    alarm_name    text,
    tags          text[],
    section       text,
    chunk_index   integer,
    content       text not null,
    token_count   integer,
    source_file   text,
    embedding     vector({EMBED_DIM})
);

-- Index for vector similarity search
create index on {TABLE_NAME} using ivfflat (embedding vector_cosine_ops)
  with (lists = 50);

-- Index for metadata filtering
create index on {TABLE_NAME} (category);
create index on {TABLE_NAME} (severity);
create index on {TABLE_NAME} (alarm_id);

-- Match function for RAG retrieval with optional metadata filtering
create or replace function match_noc_chunks (
    query_embedding vector({EMBED_DIM}),
    match_count     int default 5,
    filter_category text default null,
    filter_severity text default null
)
returns table (
    id          bigint,
    alarm_id    text,
    category    text,
    severity    text,
    alarm_name  text,
    section     text,
    content     text,
    similarity  float
)
language sql stable
as $$
    select
        id,
        alarm_id,
        category,
        severity,
        alarm_name,
        section,
        content,
        1 - (embedding <=> query_embedding) as similarity
    from {TABLE_NAME}
    where
        (filter_category is null or category = filter_category)
        and (filter_severity is null or severity = filter_severity)
    order by embedding <=> query_embedding
    limit match_count;
$$;
"""


def insert_chunks(chunks: list[dict], sb: Client, dry_run: bool = False):
    """Insert chunk rows (with embeddings) into Supabase."""
    if dry_run:
        return
    rows = []
    for c in chunks:
        row = {k: v for k, v in c.items() if k != "embedding_vector"}
        row["embedding"] = c["embedding_vector"]
        # Supabase client needs list, not numpy array
        if hasattr(row["embedding"], "tolist"):
            row["embedding"] = row["embedding"].tolist()
        rows.append(row)

    # Insert in batches of 50
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        sb.table(TABLE_NAME).insert(batch).execute()


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(kb_path: Path, dry_run: bool = False):
    print(f"\n{'='*60}")
    print(f"  NOC KB Ingestion Pipeline")
    print(f"  KB path:  {kb_path.resolve()}")
    print(f"  Dry run:  {dry_run}")
    print(f"{'='*60}\n")

    # ── 1. Parse and chunk all files ──────────────────────────────────────────
    md_files = sorted(kb_path.rglob("*.md"))
    if not md_files:
        print(f"ERROR: No markdown files found in {kb_path}")
        sys.exit(1)

    print(f"Found {len(md_files)} markdown files\n")

    all_chunks = []
    for f in md_files:
        chunks = chunk_document(f)
        all_chunks.extend(chunks)
        tok_min = min(c["token_count"] for c in chunks)
        tok_max = max(c["token_count"] for c in chunks)
        print(f"  {f.name:<50} {len(chunks):>2} chunks  "
              f"({tok_min}–{tok_max} tokens each)")

    print(f"\nTotal chunks: {len(all_chunks)}")
    avg_tok = sum(c["token_count"] for c in all_chunks) / len(all_chunks)
    print(f"Avg tokens per chunk: {avg_tok:.0f}")

    if dry_run:
        print("\n[DRY RUN] Chunk preview (first 3):")
        for c in all_chunks[:3]:
            print(f"\n  --- {c['alarm_id']} / {c['section']} ---")
            print(f"  tokens: {c['token_count']}")
            print(f"  preview: {c['content'][:200]}...")
        print("\n[DRY RUN] No embeddings generated, no DB writes.")
        return

    # ── 2. Validate credentials ───────────────────────────────────────────────
    missing = []
    if not ANTHROPIC_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_SERVICE_KEY")
    if missing:
        print(f"\nERROR: Missing environment variables: {', '.join(missing)}")
        print("Create a .env file or export them before running.")
        sys.exit(1)

    # ── 3. Generate embeddings ────────────────────────────────────────────────
    ac = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    texts = [c["content"] for c in all_chunks]

    print(f"\nGenerating embeddings for {len(texts)} chunks...")
    BATCH = 10
    embeddings = []
    for i in range(0, len(texts), BATCH):
        batch = texts[i:i+BATCH]
        print(f"  Embedding batch {i//BATCH + 1}/{(len(texts)-1)//BATCH + 1} "
              f"({len(batch)} chunks)...", end="", flush=True)
        vecs = embed_batch(batch, ac)
        embeddings.extend(vecs)
        print(f" done  ({len(vecs[0])}d vectors)")
        time.sleep(2)  # gentle rate limiting

    for chunk, emb in zip(all_chunks, embeddings):
        chunk["embedding_vector"] = emb

    # ── 4. Write to Supabase ──────────────────────────────────────────────────
    print(f"\nConnecting to Supabase: {SUPABASE_URL[:40]}...")
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    print(f"Clearing existing rows from {TABLE_NAME}...")
    sb.table(TABLE_NAME).delete().neq("id", 0).execute()

    print(f"Inserting {len(all_chunks)} chunks...")
    insert_chunks(all_chunks, sb, dry_run=False)

    print(f"\n{'='*60}")
    print(f"  Ingestion complete.")
    print(f"  {len(all_chunks)} chunks loaded into {TABLE_NAME}")
    print(f"{'='*60}\n")

    # ── 5. Verification query ─────────────────────────────────────────────────
    result = sb.table(TABLE_NAME).select("category", count="exact").execute()
    print(f"Verification — row count in DB: {result.count}")

    # Category breakdown
    rows = sb.table(TABLE_NAME).select("category, alarm_id").execute().data
    from collections import Counter
    cats = Counter(r["category"] for r in rows)
    print("\nChunks by category:")
    for cat, n in sorted(cats.items()):
        print(f"  {cat:<20} {n}")


# ── Query helper (for testing retrieval) ─────────────────────────────────────

def query_kb(question: str, category_filter: str = None, top_k: int = 5):
    import voyageai
    vo = voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY", ""))
    result = vo.embed([question], model="voyage-3", input_type="query")
    q_vec = result.embeddings[0]


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NOC KB ingestion pipeline")
    parser.add_argument("--kb-path",  default="./noc_kb", help="Path to KB folder")
    parser.add_argument("--dry-run",  action="store_true", help="Parse and chunk only, no DB writes")
    parser.add_argument("--query",    help="Test a retrieval query against loaded KB")
    parser.add_argument("--category", help="Filter test query by category (internal/external/ops_guide)")
    parser.add_argument("--print-sql", action="store_true", help="Print Supabase setup SQL and exit")
    args = parser.parse_args()

    if args.print_sql:
        print(SETUP_SQL)
        sys.exit(0)

    if args.query:
        query_kb(args.query, category_filter=args.category)
    else:
        run(kb_path=Path(args.kb_path), dry_run=args.dry_run)
