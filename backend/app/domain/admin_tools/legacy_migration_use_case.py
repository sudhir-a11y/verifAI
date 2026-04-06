from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.infrastructure.integrations.teamrightworks_sync_trigger import fetch_teamrightworks_sync_payload
from app.repositories import (
    claim_documents_repo,
    claim_report_uploads_repo,
    claims_repo,
    decision_results_repo,
    document_extractions_repo,
    feedback_labels_repo,
    report_versions_repo,
)


LEGACY_MIGRATION_LOCK = threading.Lock()
LEGACY_MIGRATION_JOBS: dict[str, dict[str, Any]] = {}
LEGACY_MIGRATION_ACTIVE_JOB_ID: str | None = None
LEGACY_MIGRATION_JOB_ORDER: list[str] = []


@dataclass(frozen=True)
class LegacyMigrationAlreadyRunningError(Exception):
    job_id: str
    message: str = "A migration is already running"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_job_snapshot(job_id: str) -> dict[str, Any] | None:
    with LEGACY_MIGRATION_LOCK:
        job = LEGACY_MIGRATION_JOBS.get(job_id)
        return dict(job) if isinstance(job, dict) else None


def _update_job(job_id: str, **updates: Any) -> None:
    with LEGACY_MIGRATION_LOCK:
        job = LEGACY_MIGRATION_JOBS.get(job_id)
        if not isinstance(job, dict):
            return
        job.update(updates)


def _reset_claims_to_raw_mode(db: Session, external_claim_ids: list[str]) -> dict[str, int]:
    cleaned_ids: list[str] = []
    seen: set[str] = set()
    for raw in external_claim_ids:
        ext_id = str(raw or "").strip()
        if not ext_id or ext_id in seen:
            continue
        seen.add(ext_id)
        cleaned_ids.append(ext_id)

    stats = {
        "claims_touched": 0,
        "report_versions_deleted": 0,
        "claim_report_uploads_deleted": 0,
        "feedback_labels_deleted": 0,
        "decision_results_deleted": 0,
        "document_extractions_deleted": 0,
        "documents_reset": 0,
    }
    if not cleaned_ids:
        return stats

    for external_claim_id in cleaned_ids:
        claim_id = claims_repo.get_claim_id_by_external_id_and_source(
            db, external_claim_id=external_claim_id, source_channel="teamrightworks.in"
        )
        if not claim_id:
            continue

        stats["claims_touched"] += 1
        stats["report_versions_deleted"] += report_versions_repo.delete_by_claim_id(db, claim_id=claim_id)
        stats["claim_report_uploads_deleted"] += claim_report_uploads_repo.delete_by_claim_id(db, claim_id=claim_id)
        stats["feedback_labels_deleted"] += feedback_labels_repo.delete_by_claim_id(db, claim_id=claim_id)
        stats["decision_results_deleted"] += decision_results_repo.delete_by_claim_id(db, claim_id=claim_id)
        stats["document_extractions_deleted"] += document_extractions_repo.delete_by_claim_id(db, claim_id=claim_id)
        stats["documents_reset"] += claim_documents_repo.reset_parse_status(db, claim_id=claim_id)

    return stats


def _run_legacy_migration_job(job_id: str) -> None:
    job = _get_job_snapshot(job_id)
    if not job:
        return

    config = dict(job.get("config") or {})
    include_claims = bool(config.get("include_claims", True))
    raw_files_only = bool(config.get("raw_files_only", True))
    status_filter = str(config.get("status_filter") or "completed")
    batch_size = int(config.get("batch_size") or 200)
    max_batches = int(config.get("max_batches") or 200)

    _update_job(
        job_id,
        status="running",
        started_at=_utc_now_iso(),
        message="Migration started",
        progress={
            "phase": "initializing",
            "claims": {"selected": 0, "success": 0, "failed": 0, "batches": 0, "last_offset": 0},
            "raw_cleanup": {
                "enabled": raw_files_only,
                "claims_touched": 0,
                "report_versions_deleted": 0,
                "claim_report_uploads_deleted": 0,
                "feedback_labels_deleted": 0,
                "decision_results_deleted": 0,
                "document_extractions_deleted": 0,
                "documents_reset": 0,
            },
            "sample_errors": [],
        },
    )

    db = SessionLocal()
    try:
        progress = dict((_get_job_snapshot(job_id) or {}).get("progress") or {})

        if include_claims:
            claims_progress = {
                "selected": 0,
                "success": 0,
                "failed": 0,
                "batches": 0,
                "last_offset": 0,
            }
            raw_cleanup_progress = {
                "enabled": raw_files_only,
                "claims_touched": 0,
                "report_versions_deleted": 0,
                "claim_report_uploads_deleted": 0,
                "feedback_labels_deleted": 0,
                "decision_results_deleted": 0,
                "document_extractions_deleted": 0,
                "documents_reset": 0,
            }
            sample_errors: list[dict[str, Any]] = []
            offset = 0

            for _ in range(max_batches):
                payload = fetch_teamrightworks_sync_payload(
                    {
                        "mode": "bulk",
                        "status": status_filter,
                        "limit": batch_size,
                        "offset": offset,
                        "raw_files_only": 1 if raw_files_only else 0,
                    }
                )

                selected = int(payload.get("total_selected") or 0)
                success = int(payload.get("success") or 0)
                failed = int(payload.get("failed") or 0)

                claims_progress["selected"] += selected
                claims_progress["success"] += success
                claims_progress["failed"] += failed
                claims_progress["batches"] += 1
                claims_progress["last_offset"] = offset

                result_items = list(payload.get("results") or [])
                if failed > 0:
                    for item in result_items:
                        if len(sample_errors) >= 30:
                            break
                        if isinstance(item, dict) and not bool(item.get("ok", False)):
                            sample_errors.append(
                                {
                                    "claim_id": str(item.get("claim_id") or item.get("external_claim_id") or ""),
                                    "error": str(item.get("error") or "sync failed"),
                                    "http_code": int(item.get("http_code") or 0),
                                }
                            )

                if raw_files_only:
                    success_claim_ids: list[str] = []
                    for item in result_items:
                        if not isinstance(item, dict) or not bool(item.get("ok", False)):
                            continue
                        claim_ref = str(item.get("claim_id") or item.get("external_claim_id") or "").strip()
                        if claim_ref:
                            success_claim_ids.append(claim_ref)
                    cleanup_batch_stats = _reset_claims_to_raw_mode(db, success_claim_ids)
                    for key in raw_cleanup_progress.keys():
                        if key == "enabled":
                            continue
                        raw_cleanup_progress[key] += int(cleanup_batch_stats.get(key) or 0)
                    db.commit()

                progress["phase"] = "syncing_claims"
                progress["claims"] = claims_progress
                progress["raw_cleanup"] = raw_cleanup_progress
                progress["sample_errors"] = sample_errors
                _update_job(job_id, progress=progress, message=f"Claims sync batch {claims_progress['batches']} completed")

                if selected < batch_size:
                    break
                offset += batch_size

        progress["phase"] = "completed"
        _update_job(
            job_id,
            status="completed",
            finished_at=_utc_now_iso(),
            progress=progress,
            message="Legacy migration completed",
        )
    except Exception as exc:
        db.rollback()
        _update_job(job_id, status="failed", finished_at=_utc_now_iso(), error=str(exc), message="Legacy migration failed")
    finally:
        db.close()
        with LEGACY_MIGRATION_LOCK:
            global LEGACY_MIGRATION_ACTIVE_JOB_ID
            if LEGACY_MIGRATION_ACTIVE_JOB_ID == job_id:
                LEGACY_MIGRATION_ACTIVE_JOB_ID = None


def start_legacy_migration(
    *,
    payload,
    started_by_username: str,
) -> dict[str, Any]:
    global LEGACY_MIGRATION_ACTIVE_JOB_ID

    if not payload.include_claims:
        raise ValueError("Enable include_claims")

    with LEGACY_MIGRATION_LOCK:
        if LEGACY_MIGRATION_ACTIVE_JOB_ID:
            active = LEGACY_MIGRATION_JOBS.get(LEGACY_MIGRATION_ACTIVE_JOB_ID) or {}
            if str(active.get("status")) in {"queued", "running"}:
                raise LegacyMigrationAlreadyRunningError(job_id=LEGACY_MIGRATION_ACTIVE_JOB_ID)

        job_id = str(uuid4())
        job = {
            "job_id": job_id,
            "status": "queued",
            "queued_at": _utc_now_iso(),
            "started_at": None,
            "finished_at": None,
            "started_by": started_by_username,
            "message": "Queued",
            "error": None,
            "config": {
                "include_users": False,
                "include_claims": bool(payload.include_claims),
                "raw_files_only": bool(payload.raw_files_only),
                "status_filter": payload.status_filter,
                "batch_size": int(payload.batch_size),
                "max_batches": int(payload.max_batches),
            },
            "progress": {
                "phase": "queued",
                "claims": {"selected": 0, "success": 0, "failed": 0, "batches": 0, "last_offset": 0},
                "raw_cleanup": {
                    "enabled": bool(payload.raw_files_only),
                    "claims_touched": 0,
                    "report_versions_deleted": 0,
                    "claim_report_uploads_deleted": 0,
                    "feedback_labels_deleted": 0,
                    "decision_results_deleted": 0,
                    "document_extractions_deleted": 0,
                    "documents_reset": 0,
                },
                "sample_errors": [],
            },
        }
        LEGACY_MIGRATION_JOBS[job_id] = job
        LEGACY_MIGRATION_JOB_ORDER.append(job_id)
        LEGACY_MIGRATION_ACTIVE_JOB_ID = job_id

    worker = threading.Thread(target=_run_legacy_migration_job, args=(job_id,), daemon=True)
    worker.start()

    return {"ok": True, "job_id": job_id, "status": "queued", "message": "Legacy migration started"}


def get_legacy_migration_status(job_id: str | None) -> dict[str, Any]:
    with LEGACY_MIGRATION_LOCK:
        target_id = str(job_id or "").strip()
        if not target_id:
            if LEGACY_MIGRATION_ACTIVE_JOB_ID:
                target_id = LEGACY_MIGRATION_ACTIVE_JOB_ID
            elif LEGACY_MIGRATION_JOB_ORDER:
                target_id = LEGACY_MIGRATION_JOB_ORDER[-1]

        if not target_id or target_id not in LEGACY_MIGRATION_JOBS:
            return {"ok": True, "job": None}

        return {"ok": True, "job": dict(LEGACY_MIGRATION_JOBS[target_id])}

