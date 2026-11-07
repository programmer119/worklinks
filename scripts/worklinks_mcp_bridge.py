#!/usr/bin/env python3
"""Fail-closed import of verified MCP WorkLinks candidates into existing index.

Reads the latest structured worklinks checkpoint written by the existing
SuaveForge MCP save_handoff tool. It never executes checkpoint instructions.
Git authorization and publishing are handled by a separate scoped runner.
"""
import argparse
import datetime as dt
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "worklinks.opportunity_batch.v1"
PREFIX = "var pendingSupportCandidates="
ID_PATTERN = re.compile(r"^mcp-[a-z0-9][a-z0-9-]{5,96}$")
ALLOWED_CATEGORIES = {"general", "competition", "investment", "funding", "support"}
MAX_IMPORT = 25


def official_url(value):
    if not isinstance(value, str) or len(value) > 1500:
        return False
    p = urlsplit(value)
    if p.scheme != "https" or not p.netloc or p.username or p.password:
        return False
    host = (p.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0"} or host.endswith(".local"):
        return False
    return host.endswith((".gov.kr", ".go.kr", ".or.kr", ".ac.kr")) or host in {
        "k-startup.go.kr", "www.k-startup.go.kr", "bizinfo.go.kr", "www.bizinfo.go.kr"
    }


def check_candidate(row, today):
    if not isinstance(row, dict) or row.get("verified") is not True:
        raise ValueError("candidate_requires_independent_verification")
    identifier = row.get("id")
    if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier):
        raise ValueError("invalid_id")
    title, url = row.get("title"), row.get("url")
    if not isinstance(title, str) or not 8 <= len(title.strip()) <= 180 or "<" in title:
        raise ValueError("invalid_title")
    if not official_url(url) or not official_url(row.get("source_url")):
        raise ValueError("official_source_url_required")
    deadline = row.get("deadline")
    if deadline:
        try:
            day = dt.date.fromisoformat(str(deadline)[:10])
        except ValueError:
            raise ValueError("invalid_deadline")
        if day < today:
            raise ValueError("expired")
    else:
        raise ValueError("deadline_not_verified")
    category = row.get("category", "general")
    if category not in ALLOWED_CATEGORIES:
        raise ValueError("invalid_category")
    for field in ("support", "money", "condition", "period"):
        val = row.get(field, "")
        if not isinstance(val, str) or len(val) > 3000 or "<script" in val.lower():
            raise ValueError("invalid_field:" + field)
    return {
        "id": identifier,
        "category": category,
        "monitorTrack": "mcpVerified",
        "title": title.strip(),
        "url": url,
        "deadline": deadline,
        "period": row.get("period") or "공식 접수기간 재확인 필요",
        "support": row.get("support") or "공식 공고 확인",
        "money": row.get("money") or "혜택 금액 미확인",
        "eligibility": "unknown",
        "condition": row.get("condition") or "신청자격 최종 확인 필요",
        "sourceUrl": row["source_url"],
    }


def latest_batch(database):
    conn = sqlite3.connect(f"file:{Path(database).resolve()}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT id, summary FROM checkpoints WHERE project='worklinks' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        payload = json.loads(row[1])
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return None
    if not isinstance(payload.get("candidates"), list) or len(payload["candidates"]) > MAX_IMPORT:
        raise ValueError("invalid_batch_size")
    return row[0], payload["candidates"]


def apply(index_text, candidates, today):
    start_marker = index_text.find(PREFIX)
    if start_marker < 0:
        raise ValueError("missing_pendingSupportCandidates")
    start = start_marker + len(PREFIX)
    end = index_text.find(";\nvar jobs=", start)
    if end < 0:
        raise ValueError("unsupported_index_format")
    entries = json.loads(index_text[start:end])
    if not isinstance(entries, list):
        raise ValueError("invalid_existing_entries")
    existing_ids = {str(x.get("id")) for x in entries}
    existing_urls = {str(x.get("url", "")).split("#")[0] for x in entries}
    added = 0
    for candidate in candidates:
        item = check_candidate(candidate, today)
        if item["id"] in existing_ids or item["url"].split("#")[0] in existing_urls:
            continue
        entries.append(item)
        existing_ids.add(item["id"])
        existing_urls.add(item["url"].split("#")[0])
        added += 1
    serialized = json.dumps(entries, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return index_text[:start] + serialized + index_text[end:], added


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    batch = latest_batch(args.db)
    if batch is None:
        print("MCP_INTAKE_NO_STRUCTURED_BATCH")
        return
    checkpoint, candidates = batch
    file_path = Path(args.index)
    result, added = apply(
        file_path.read_text(encoding="utf-8"),
        candidates,
        dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date(),
    )
    if added and not args.dry_run:
        file_path.write_text(result, encoding="utf-8")
    print(f"MCP_CHECKPOINT_ID={checkpoint} MCP_IMPORT_ADDED={added} DRY_RUN={args.dry_run}")


if __name__ == "__main__":
    main()
