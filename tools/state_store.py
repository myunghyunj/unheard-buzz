import csv
import hashlib
import json
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

try:  # pragma: no cover - optional dependency
    import duckdb  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    duckdb = None

from config import Instruction, SocialPost, StateStoreConfig
from schema_versions import PROGRAM_CONTRACT_VERSION, schema_version


def _normalize_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def instruction_hash(instruction: Instruction) -> str:
    payload = json.dumps(asdict(instruction), ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def default_project_id(instruction: Instruction) -> str:
    project_id = (instruction.state_store.project_id or "").strip()
    if project_id:
        return project_id
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in instruction.project_name).strip("_")
    return slug or "default_project"


def build_run_id(project_id: str, completed_at: str, run_label: str = "") -> str:
    seed = f"{project_id}|{completed_at}|{run_label}".encode("utf-8")
    try:
        dt = datetime.fromisoformat((completed_at or "").replace("Z", "+00:00")).astimezone(timezone.utc)
        stamp = dt.strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        stamp = "".join(ch for ch in (completed_at or "") if ch.isalnum())[:16] or "unknown"
    return f"run_{stamp}_{hashlib.sha1(seed).hexdigest()[:8]}"


def _load_csv_rows(path: str) -> List[dict]:
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _load_json(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


class LocalStateStore:
    def __init__(self, config: StateStoreConfig):
        self.requested_backend = (config.backend or "sqlite").strip().lower()
        self.path = config.path
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

        if self.requested_backend == "duckdb" and duckdb is not None:
            self.resolved_backend = "duckdb"
            self.conn = duckdb.connect(self.path)
        else:
            self.resolved_backend = "sqlite"
            self.conn = sqlite3.connect(self.path)
            self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def _execute(self, sql: str, params: Tuple = ()) -> None:
        self.conn.execute(sql, params)

    def _fetchall(self, sql: str, params: Tuple = ()) -> List[tuple]:
        return self.conn.execute(sql, params).fetchall()

    def _table_columns(self, table: str) -> set:
        try:
            rows = self._fetchall(f"PRAGMA table_info('{table}')")
        except Exception:
            return set()
        return {row[1] for row in rows if len(row) > 1}

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        if column in self._table_columns(table):
            return
        self._execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _ensure_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                case_id TEXT,
                run_label TEXT,
                started_at TEXT,
                completed_at TEXT,
                instruction_hash TEXT,
                git_commit TEXT,
                output_dir TEXT,
                requested_backend TEXT,
                resolved_backend TEXT,
                manifest_path TEXT,
                artifact_inventory_path TEXT,
                schema_version TEXT,
                program_contract_version TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS posts (
                project_id TEXT NOT NULL,
                post_id TEXT NOT NULL,
                latest_run_id TEXT NOT NULL,
                first_seen_run_id TEXT,
                last_seen_run_id TEXT,
                platform TEXT,
                source_id TEXT,
                source_family TEXT,
                source_tier INTEGER,
                author TEXT,
                text TEXT,
                timestamp TEXT,
                url TEXT,
                normalized_text TEXT,
                relevance_score REAL,
                final_rank_score REAL,
                canonical_issue_id TEXT,
                PRIMARY KEY (project_id, post_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS issues (
                project_id TEXT NOT NULL,
                canonical_issue_id TEXT NOT NULL,
                latest_run_id TEXT NOT NULL,
                first_seen_run_id TEXT,
                last_seen_run_id TEXT,
                normalized_problem_statement TEXT,
                opportunity_score REAL,
                confidence_score REAL,
                priority_score REAL,
                evidence_count INTEGER,
                independent_source_count INTEGER,
                source_family_count INTEGER,
                score_breakdown_json TEXT,
                PRIMARY KEY (project_id, canonical_issue_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS evidence (
                project_id TEXT NOT NULL,
                evidence_key TEXT NOT NULL,
                evidence_id TEXT,
                canonical_issue_id TEXT,
                post_id TEXT,
                latest_run_id TEXT NOT NULL,
                first_seen_run_id TEXT,
                last_seen_run_id TEXT,
                source_family TEXT,
                source_tier INTEGER,
                evidence_class TEXT,
                trust_weight REAL,
                publication_date TEXT,
                independence_key TEXT,
                excerpt TEXT,
                url TEXT,
                platform TEXT,
                PRIMARY KEY (project_id, evidence_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sources (
                project_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                source_id TEXT NOT NULL,
                latest_run_id TEXT NOT NULL,
                first_seen_run_id TEXT,
                last_seen_run_id TEXT,
                source_title TEXT,
                source_family TEXT,
                source_tier INTEGER,
                url TEXT,
                PRIMARY KEY (project_id, platform, source_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS issue_run_metrics (
                project_id TEXT NOT NULL,
                canonical_issue_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                evidence_count INTEGER,
                independent_source_count INTEGER,
                priority_score REAL,
                delta_vs_prev REAL,
                status_label TEXT,
                lifecycle_state TEXT,
                transition_reason TEXT,
                PRIMARY KEY (project_id, canonical_issue_id, run_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS entities (
                project_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                latest_run_id TEXT NOT NULL,
                first_seen_run_id TEXT,
                last_seen_run_id TEXT,
                entity_type TEXT,
                canonical_name TEXT,
                normalized_name TEXT,
                supporting_issue_count INTEGER,
                mention_count INTEGER,
                PRIMARY KEY (project_id, entity_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS issue_entity_links (
                project_id TEXT NOT NULL,
                link_key TEXT NOT NULL,
                latest_run_id TEXT NOT NULL,
                first_seen_run_id TEXT,
                last_seen_run_id TEXT,
                canonical_issue_id TEXT,
                entity_id TEXT,
                entity_type TEXT,
                canonical_name TEXT,
                link_type TEXT,
                confidence REAL,
                provenance TEXT,
                PRIMARY KEY (project_id, link_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS benchmark_documents (
                project_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                latest_run_id TEXT NOT NULL,
                first_seen_run_id TEXT,
                last_seen_run_id TEXT,
                source_type TEXT,
                source_family TEXT,
                source_tier INTEGER,
                entity_id TEXT,
                title TEXT,
                url TEXT,
                publication_date TEXT,
                text_excerpt TEXT,
                provenance TEXT,
                tags_json TEXT,
                PRIMARY KEY (project_id, doc_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS benchmark_claims (
                project_id TEXT NOT NULL,
                claim_id TEXT NOT NULL,
                latest_run_id TEXT NOT NULL,
                first_seen_run_id TEXT,
                last_seen_run_id TEXT,
                doc_id TEXT,
                entity_id TEXT,
                claim_text TEXT,
                claim_type TEXT,
                polarity TEXT,
                publication_date TEXT,
                url TEXT,
                PRIMARY KEY (project_id, claim_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS contradiction_records (
                project_id TEXT NOT NULL,
                contradiction_id TEXT NOT NULL,
                latest_run_id TEXT NOT NULL,
                first_seen_run_id TEXT,
                last_seen_run_id TEXT,
                contradiction_type TEXT,
                canonical_issue_id TEXT,
                entity_id TEXT,
                left_evidence TEXT,
                right_evidence TEXT,
                summary TEXT,
                PRIMARY KEY (project_id, contradiction_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS review_decisions (
                project_id TEXT NOT NULL,
                case_id TEXT,
                record_type TEXT NOT NULL,
                record_id TEXT NOT NULL,
                field TEXT NOT NULL,
                override_value TEXT,
                notes TEXT,
                annotation_origin TEXT,
                source_path TEXT,
                latest_run_id TEXT NOT NULL,
                first_seen_run_id TEXT,
                last_seen_run_id TEXT,
                PRIMARY KEY (project_id, record_type, record_id, field)
            )
            """,
        ]
        for statement in statements:
            self._execute(statement)
        self._ensure_column("runs", "case_id", "TEXT")
        self._ensure_column("runs", "manifest_path", "TEXT")
        self._ensure_column("runs", "artifact_inventory_path", "TEXT")
        self._ensure_column("runs", "schema_version", "TEXT")
        self._ensure_column("runs", "program_contract_version", "TEXT")
        self._ensure_column("issue_run_metrics", "lifecycle_state", "TEXT")
        self._ensure_column("issue_run_metrics", "transition_reason", "TEXT")
        self.conn.commit()

    def ingest_run(
        self,
        *,
        run_record: Dict[str, str],
        instruction: Instruction,
        posts: List[SocialPost],
        generated_files: Dict[str, str],
    ) -> Dict[str, int]:
        project_id = run_record["project_id"]
        run_id = run_record["run_id"]
        issue_rows = _load_csv_rows(generated_files.get("issue_registry_csv", ""))
        evidence_rows = _load_csv_rows(generated_files.get("evidence_registry_csv", ""))
        entity_rows = _load_csv_rows(generated_files.get("entity_registry_csv", ""))
        issue_entity_link_rows = _load_csv_rows(generated_files.get("issue_entity_links_csv", ""))
        contradiction_rows = _load_csv_rows(generated_files.get("contradiction_registry_csv", ""))
        benchmark_coverage = _load_json(generated_files.get("benchmark_coverage_json", ""))
        benchmark_document_rows = list(benchmark_coverage.get("benchmark_documents", []) or [])
        benchmark_claim_rows = list(benchmark_coverage.get("benchmark_claims", []) or [])

        self._execute(
            """
            INSERT INTO runs (
                run_id, project_id, case_id, run_label, started_at, completed_at, instruction_hash,
                git_commit, output_dir, requested_backend, resolved_backend, manifest_path,
                artifact_inventory_path, schema_version, program_contract_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                project_id=excluded.project_id,
                case_id=excluded.case_id,
                run_label=excluded.run_label,
                started_at=excluded.started_at,
                completed_at=excluded.completed_at,
                instruction_hash=excluded.instruction_hash,
                git_commit=excluded.git_commit,
                output_dir=excluded.output_dir,
                requested_backend=excluded.requested_backend,
                resolved_backend=excluded.resolved_backend,
                manifest_path=excluded.manifest_path,
                artifact_inventory_path=excluded.artifact_inventory_path,
                schema_version=excluded.schema_version,
                program_contract_version=excluded.program_contract_version
            """,
            (
                run_id,
                project_id,
                run_record.get("case_id", ""),
                run_record.get("run_label", ""),
                run_record.get("started_at", ""),
                run_record.get("completed_at", ""),
                run_record.get("instruction_hash", ""),
                run_record.get("git_commit", ""),
                run_record.get("output_dir", ""),
                run_record.get("requested_backend", self.requested_backend),
                run_record.get("resolved_backend", self.resolved_backend),
                run_record.get("manifest_path", ""),
                run_record.get("artifact_inventory_path", ""),
                run_record.get("schema_version", schema_version("run_manifest")),
                run_record.get("program_contract_version", PROGRAM_CONTRACT_VERSION),
            ),
        )

        for post in posts:
            text_value = post.text if instruction.state_store.keep_raw_text else ""
            self._execute(
                """
                INSERT INTO posts (
                    project_id, post_id, latest_run_id, first_seen_run_id, last_seen_run_id, platform,
                    source_id, source_family, source_tier, author, text, timestamp, url,
                    normalized_text, relevance_score, final_rank_score, canonical_issue_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, post_id) DO UPDATE SET
                    latest_run_id=excluded.latest_run_id,
                    last_seen_run_id=excluded.last_seen_run_id,
                    platform=excluded.platform,
                    source_id=excluded.source_id,
                    source_family=excluded.source_family,
                    source_tier=excluded.source_tier,
                    author=excluded.author,
                    text=excluded.text,
                    timestamp=excluded.timestamp,
                    url=excluded.url,
                    normalized_text=excluded.normalized_text,
                    relevance_score=excluded.relevance_score,
                    final_rank_score=excluded.final_rank_score,
                    canonical_issue_id=excluded.canonical_issue_id
                """,
                (
                    project_id,
                    post.post_id,
                    run_id,
                    run_id,
                    run_id,
                    post.platform,
                    post.source_id,
                    post.source_family,
                    int(post.source_tier or 0),
                    post.author,
                    text_value,
                    post.timestamp,
                    post.url,
                    _normalize_text(post.text),
                    float(post.relevance_score or 0.0),
                    float(post.final_rank_score or 0.0),
                    post.canonical_issue_id,
                ),
            )
            self._execute(
                """
                INSERT INTO sources (
                    project_id, platform, source_id, latest_run_id, first_seen_run_id, last_seen_run_id,
                    source_title, source_family, source_tier, url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, platform, source_id) DO UPDATE SET
                    latest_run_id=excluded.latest_run_id,
                    last_seen_run_id=excluded.last_seen_run_id,
                    source_title=excluded.source_title,
                    source_family=excluded.source_family,
                    source_tier=excluded.source_tier,
                    url=excluded.url
                """,
                (
                    project_id,
                    post.platform,
                    post.source_id,
                    run_id,
                    run_id,
                    run_id,
                    post.source_title,
                    post.source_family,
                    int(post.source_tier or 0),
                    post.url,
                ),
            )

        for issue in issue_rows:
            breakdown = issue.get("score_breakdown_json", "")
            self._execute(
                """
                INSERT INTO issues (
                    project_id, canonical_issue_id, latest_run_id, first_seen_run_id, last_seen_run_id,
                    normalized_problem_statement, opportunity_score, confidence_score, priority_score,
                    evidence_count, independent_source_count, source_family_count, score_breakdown_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, canonical_issue_id) DO UPDATE SET
                    latest_run_id=excluded.latest_run_id,
                    last_seen_run_id=excluded.last_seen_run_id,
                    normalized_problem_statement=excluded.normalized_problem_statement,
                    opportunity_score=excluded.opportunity_score,
                    confidence_score=excluded.confidence_score,
                    priority_score=excluded.priority_score,
                    evidence_count=excluded.evidence_count,
                    independent_source_count=excluded.independent_source_count,
                    source_family_count=excluded.source_family_count,
                    score_breakdown_json=excluded.score_breakdown_json
                """,
                (
                    project_id,
                    issue.get("canonical_issue_id", ""),
                    run_id,
                    run_id,
                    run_id,
                    issue.get("normalized_problem_statement", ""),
                    float(issue.get("opportunity_score", 0.0) or 0.0),
                    float(issue.get("confidence_score", 0.0) or 0.0),
                    float(issue.get("priority_score", 0.0) or 0.0),
                    int(issue.get("evidence_count", 0) or 0),
                    int(issue.get("independent_source_count", 0) or 0),
                    int(issue.get("source_family_count", 0) or 0),
                    breakdown,
                ),
            )
            self._execute(
                """
                INSERT INTO issue_run_metrics (
                    project_id, canonical_issue_id, run_id, evidence_count, independent_source_count,
                    priority_score, delta_vs_prev, status_label, lifecycle_state, transition_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, canonical_issue_id, run_id) DO UPDATE SET
                    evidence_count=excluded.evidence_count,
                    independent_source_count=excluded.independent_source_count,
                    priority_score=excluded.priority_score,
                    delta_vs_prev=excluded.delta_vs_prev,
                    status_label=excluded.status_label,
                    lifecycle_state=excluded.lifecycle_state,
                    transition_reason=excluded.transition_reason
                """,
                (
                    project_id,
                    issue.get("canonical_issue_id", ""),
                    run_id,
                    int(issue.get("evidence_count", 0) or 0),
                    int(issue.get("independent_source_count", 0) or 0),
                    float(issue.get("priority_score", 0.0) or 0.0),
                    None,
                    "",
                    "",
                    "",
                ),
            )

        for evidence in evidence_rows:
            evidence_key = self._evidence_key(project_id, evidence)
            self._execute(
                """
                INSERT INTO evidence (
                    project_id, evidence_key, evidence_id, canonical_issue_id, post_id, latest_run_id,
                    first_seen_run_id, last_seen_run_id, source_family, source_tier, evidence_class,
                    trust_weight, publication_date, independence_key, excerpt, url, platform
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, evidence_key) DO UPDATE SET
                    evidence_id=excluded.evidence_id,
                    canonical_issue_id=excluded.canonical_issue_id,
                    post_id=excluded.post_id,
                    latest_run_id=excluded.latest_run_id,
                    last_seen_run_id=excluded.last_seen_run_id,
                    source_family=excluded.source_family,
                    source_tier=excluded.source_tier,
                    evidence_class=excluded.evidence_class,
                    trust_weight=excluded.trust_weight,
                    publication_date=excluded.publication_date,
                    independence_key=excluded.independence_key,
                    excerpt=excluded.excerpt,
                    url=excluded.url,
                    platform=excluded.platform
                """,
                (
                    project_id,
                    evidence_key,
                    evidence.get("evidence_id", ""),
                    evidence.get("canonical_issue_id", ""),
                    evidence.get("post_id", ""),
                    run_id,
                    run_id,
                    run_id,
                    evidence.get("source_family", ""),
                    int(evidence.get("source_tier", 0) or 0),
                    evidence.get("evidence_class", ""),
                    float(evidence.get("trust_weight", 0.0) or 0.0),
                    evidence.get("publication_date", ""),
                    evidence.get("independence_key", ""),
                    evidence.get("excerpt", ""),
                    evidence.get("url", ""),
                    evidence.get("platform", ""),
                ),
            )

        for entity in entity_rows:
            self._execute(
                """
                INSERT INTO entities (
                    project_id, entity_id, latest_run_id, first_seen_run_id, last_seen_run_id,
                    entity_type, canonical_name, normalized_name, supporting_issue_count, mention_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, entity_id) DO UPDATE SET
                    latest_run_id=excluded.latest_run_id,
                    last_seen_run_id=excluded.last_seen_run_id,
                    entity_type=excluded.entity_type,
                    canonical_name=excluded.canonical_name,
                    normalized_name=excluded.normalized_name,
                    supporting_issue_count=excluded.supporting_issue_count,
                    mention_count=excluded.mention_count
                """,
                (
                    project_id,
                    entity.get("entity_id", ""),
                    run_id,
                    run_id,
                    run_id,
                    entity.get("entity_type", ""),
                    entity.get("canonical_name", ""),
                    entity.get("normalized_name", ""),
                    int(entity.get("supporting_issue_count", 0) or 0),
                    int(entity.get("mention_count", 0) or 0),
                ),
            )

        for link in issue_entity_link_rows:
            link_key = hashlib.sha1(
                "|".join(
                    [
                        project_id,
                        link.get("canonical_issue_id", ""),
                        link.get("entity_id", ""),
                        link.get("link_type", ""),
                        link.get("provenance", ""),
                    ]
                ).encode("utf-8")
            ).hexdigest()
            self._execute(
                """
                INSERT INTO issue_entity_links (
                    project_id, link_key, latest_run_id, first_seen_run_id, last_seen_run_id,
                    canonical_issue_id, entity_id, entity_type, canonical_name, link_type,
                    confidence, provenance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, link_key) DO UPDATE SET
                    latest_run_id=excluded.latest_run_id,
                    last_seen_run_id=excluded.last_seen_run_id,
                    canonical_issue_id=excluded.canonical_issue_id,
                    entity_id=excluded.entity_id,
                    entity_type=excluded.entity_type,
                    canonical_name=excluded.canonical_name,
                    link_type=excluded.link_type,
                    confidence=excluded.confidence,
                    provenance=excluded.provenance
                """,
                (
                    project_id,
                    link_key,
                    run_id,
                    run_id,
                    run_id,
                    link.get("canonical_issue_id", ""),
                    link.get("entity_id", ""),
                    link.get("entity_type", ""),
                    link.get("canonical_name", ""),
                    link.get("link_type", ""),
                    float(link.get("confidence", 0.0) or 0.0),
                    link.get("provenance", ""),
                ),
            )

        for document in benchmark_document_rows:
            self._execute(
                """
                INSERT INTO benchmark_documents (
                    project_id, doc_id, latest_run_id, first_seen_run_id, last_seen_run_id,
                    source_type, source_family, source_tier, entity_id, title, url,
                    publication_date, text_excerpt, provenance, tags_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, doc_id) DO UPDATE SET
                    latest_run_id=excluded.latest_run_id,
                    last_seen_run_id=excluded.last_seen_run_id,
                    source_type=excluded.source_type,
                    source_family=excluded.source_family,
                    source_tier=excluded.source_tier,
                    entity_id=excluded.entity_id,
                    title=excluded.title,
                    url=excluded.url,
                    publication_date=excluded.publication_date,
                    text_excerpt=excluded.text_excerpt,
                    provenance=excluded.provenance,
                    tags_json=excluded.tags_json
                """,
                (
                    project_id,
                    document.get("doc_id", ""),
                    run_id,
                    run_id,
                    run_id,
                    document.get("source_type", ""),
                    document.get("source_family", ""),
                    int(document.get("source_tier", 0) or 0),
                    document.get("entity_id", ""),
                    document.get("title", ""),
                    document.get("url", ""),
                    document.get("publication_date", ""),
                    document.get("text_excerpt", ""),
                    document.get("provenance", ""),
                    json.dumps(document.get("tags", []) or [], ensure_ascii=False, sort_keys=True),
                ),
            )

        for claim in benchmark_claim_rows:
            self._execute(
                """
                INSERT INTO benchmark_claims (
                    project_id, claim_id, latest_run_id, first_seen_run_id, last_seen_run_id,
                    doc_id, entity_id, claim_text, claim_type, polarity, publication_date, url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, claim_id) DO UPDATE SET
                    latest_run_id=excluded.latest_run_id,
                    last_seen_run_id=excluded.last_seen_run_id,
                    doc_id=excluded.doc_id,
                    entity_id=excluded.entity_id,
                    claim_text=excluded.claim_text,
                    claim_type=excluded.claim_type,
                    polarity=excluded.polarity,
                    publication_date=excluded.publication_date,
                    url=excluded.url
                """,
                (
                    project_id,
                    claim.get("claim_id", ""),
                    run_id,
                    run_id,
                    run_id,
                    claim.get("doc_id", ""),
                    claim.get("entity_id", ""),
                    claim.get("claim_text", ""),
                    claim.get("claim_type", ""),
                    claim.get("polarity", ""),
                    claim.get("publication_date", ""),
                    claim.get("url", ""),
                ),
            )

        for contradiction in contradiction_rows:
            self._execute(
                """
                INSERT INTO contradiction_records (
                    project_id, contradiction_id, latest_run_id, first_seen_run_id, last_seen_run_id,
                    contradiction_type, canonical_issue_id, entity_id, left_evidence, right_evidence, summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, contradiction_id) DO UPDATE SET
                    latest_run_id=excluded.latest_run_id,
                    last_seen_run_id=excluded.last_seen_run_id,
                    contradiction_type=excluded.contradiction_type,
                    canonical_issue_id=excluded.canonical_issue_id,
                    entity_id=excluded.entity_id,
                    left_evidence=excluded.left_evidence,
                    right_evidence=excluded.right_evidence,
                    summary=excluded.summary
                """,
                (
                    project_id,
                    contradiction.get("contradiction_id", ""),
                    run_id,
                    run_id,
                    run_id,
                    contradiction.get("contradiction_type", ""),
                    contradiction.get("canonical_issue_id", ""),
                    contradiction.get("entity_id", ""),
                    contradiction.get("left_evidence", ""),
                    contradiction.get("right_evidence", ""),
                    contradiction.get("summary", ""),
                ),
            )

        self.conn.commit()
        return {
            "posts": len(posts),
            "issues": len(issue_rows),
            "evidence": len(evidence_rows),
            "entities": len(entity_rows),
            "issue_entity_links": len(issue_entity_link_rows),
            "benchmark_documents": len(benchmark_document_rows),
            "benchmark_claims": len(benchmark_claim_rows),
            "contradictions": len(contradiction_rows),
        }

    def _evidence_key(self, project_id: str, evidence: dict) -> str:
        payload = "|".join(
            [
                project_id,
                evidence.get("canonical_issue_id", ""),
                evidence.get("post_id", ""),
                evidence.get("independence_key", ""),
                (evidence.get("excerpt", "") or "")[:180],
            ]
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def recent_runs(self, project_id: str, lookback_runs: int, exclude_run_id: str = "") -> List[dict]:
        rows = self._fetchall(
            """
            SELECT run_id, project_id, run_label, started_at, completed_at
            FROM runs
            WHERE project_id = ? AND run_id != ?
            ORDER BY completed_at DESC
            LIMIT ?
            """,
            (project_id, exclude_run_id, int(max(1, lookback_runs))),
        )
        return [
            {
                "run_id": row[0],
                "project_id": row[1],
                "run_label": row[2],
                "started_at": row[3],
                "completed_at": row[4],
            }
            for row in rows
        ]

    def issue_metrics_for_run(self, project_id: str, run_id: str) -> Dict[str, dict]:
        rows = self._fetchall(
            """
            SELECT m.canonical_issue_id, m.evidence_count, m.independent_source_count, m.priority_score,
                   i.normalized_problem_statement
            FROM issue_run_metrics m
            LEFT JOIN issues i
              ON i.project_id = m.project_id AND i.canonical_issue_id = m.canonical_issue_id
            WHERE m.project_id = ? AND m.run_id = ?
            """,
            (project_id, run_id),
        )
        return {
            row[0]: {
                "canonical_issue_id": row[0],
                "evidence_count": int(row[1] or 0),
                "independent_source_count": int(row[2] or 0),
                "priority_score": float(row[3] or 0.0),
                "normalized_problem_statement": row[4] or "",
            }
            for row in rows
        }

    def update_issue_run_metrics(self, project_id: str, run_id: str, rows: Iterable[dict]) -> None:
        for row in rows:
            self._execute(
                """
                UPDATE issue_run_metrics
                SET delta_vs_prev = ?, status_label = ?, lifecycle_state = ?, transition_reason = ?
                WHERE project_id = ? AND canonical_issue_id = ? AND run_id = ?
                """,
                (
                    float(row.get("delta_vs_prev", 0.0) or 0.0),
                    row.get("status_label", ""),
                    row.get("lifecycle_state", ""),
                    row.get("transition_reason", ""),
                    project_id,
                    row.get("canonical_issue_id", ""),
                    run_id,
                ),
            )
        self.conn.commit()

    def update_run_artifacts(
        self,
        *,
        run_id: str,
        manifest_path: str = "",
        artifact_inventory_path: str = "",
        completed_at: str = "",
    ) -> None:
        self._execute(
            """
            UPDATE runs
            SET manifest_path = ?, artifact_inventory_path = ?, completed_at = COALESCE(NULLIF(?, ''), completed_at)
            WHERE run_id = ?
            """,
            (manifest_path, artifact_inventory_path, completed_at, run_id),
        )
        self.conn.commit()

    def save_reviewer_annotations(
        self,
        *,
        project_id: str,
        case_id: str,
        run_id: str,
        annotations: List[dict],
        source_path: str = "input/reviewer_annotations.csv",
    ) -> None:
        for row in annotations:
            record_type = str(row.get("record_type", "") or "").strip()
            record_id = str(row.get("record_id", "") or "").strip()
            field = str(row.get("field", "") or "").strip()
            if not record_type or not record_id or not field:
                continue
            self._execute(
                """
                INSERT INTO review_decisions (
                    project_id, case_id, record_type, record_id, field, override_value, notes,
                    annotation_origin, source_path, latest_run_id, first_seen_run_id, last_seen_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, record_type, record_id, field) DO UPDATE SET
                    case_id=excluded.case_id,
                    override_value=excluded.override_value,
                    notes=excluded.notes,
                    annotation_origin=excluded.annotation_origin,
                    source_path=excluded.source_path,
                    latest_run_id=excluded.latest_run_id,
                    last_seen_run_id=excluded.last_seen_run_id
                """,
                (
                    project_id,
                    case_id,
                    record_type,
                    record_id,
                    field,
                    row.get("override_value", ""),
                    row.get("notes", ""),
                    row.get("annotation_origin", "manual_csv"),
                    source_path,
                    run_id,
                    run_id,
                    run_id,
                ),
            )
        self.conn.commit()

    def latest_reviewer_annotations(
        self,
        *,
        project_id: str,
        case_id: str = "",
        exclude_run_id: str = "",
        limit: int = 200,
    ) -> List[dict]:
        sql = """
            SELECT record_type, record_id, field, override_value, notes, annotation_origin, source_path, last_seen_run_id
            FROM review_decisions
            WHERE project_id = ?
        """
        params: List = [project_id]
        if case_id:
            sql += " AND case_id = ?"
            params.append(case_id)
        if exclude_run_id:
            sql += " AND last_seen_run_id != ?"
            params.append(exclude_run_id)
        sql += " ORDER BY last_seen_run_id DESC, record_type ASC, record_id ASC LIMIT ?"
        params.append(int(max(1, limit)))
        rows = self._fetchall(sql, tuple(params))
        return [
            {
                "record_type": row[0] or "",
                "record_id": row[1] or "",
                "field": row[2] or "",
                "override_value": row[3] or "",
                "notes": row[4] or "",
                "annotation_origin": "review_memory",
                "stored_annotation_origin": row[5] or "",
                "source_path": row[6] or "",
                "source_run_id": row[7] or "",
            }
            for row in rows
        ]


def build_run_record(
    *,
    instruction: Instruction,
    output_dir: str,
    started_at: str,
    completed_at: str,
    git_commit: str,
    run_label: str = "",
    project_id_override: str = "",
    requested_backend: str = "",
    resolved_backend: str = "",
) -> Dict[str, str]:
    project_id = (project_id_override or default_project_id(instruction)).strip()
    run_id = build_run_id(project_id, completed_at, run_label)
    case_id = (instruction.case.case_id or "").strip() or project_id
    return {
        "schema_version": schema_version("run_manifest"),
        "program_contract_version": PROGRAM_CONTRACT_VERSION,
        "run_id": run_id,
        "project_id": project_id,
        "case_id": case_id,
        "run_label": run_label,
        "started_at": started_at,
        "completed_at": completed_at,
        "instruction_hash": instruction_hash(instruction),
        "git_commit": git_commit,
        "output_dir": output_dir,
        "requested_backend": requested_backend or instruction.state_store.backend,
        "resolved_backend": resolved_backend or instruction.state_store.backend,
    }
