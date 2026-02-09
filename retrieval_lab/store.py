"""
MongoDB integration: embedding cache (via benchmark_store when available) and
retrieval_lab_experiments collection for experiment tracking over time.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RETRIEVAL_LAB_EXPERIMENTS_COLLECTION = "retrieval_lab_experiments"
DEFAULT_RULESLAWYER_DB_NAME = "ruleslawyer"
RULESLAWYER_DB_NAME_ENV = "RULESLAWYER_DB_NAME"


def _get_mongo_client(mongo_uri: Optional[str] = None):
    try:
        from pymongo import MongoClient
    except ImportError:
        raise RuntimeError("pymongo is required for Retrieval Lab MongoDB support. Install with: pip install pymongo")
    uri = mongo_uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    return MongoClient(uri)


def _get_ruleslawyer_db_name() -> str:
    return os.getenv(RULESLAWYER_DB_NAME_ENV, DEFAULT_RULESLAWYER_DB_NAME)


def get_retrieval_lab_experiments_collection(client, db_name: Optional[str] = None):
    """Return the retrieval_lab_experiments collection in the ruleslawyer DB."""
    db = client[db_name or _get_ruleslawyer_db_name()]
    return db[RETRIEVAL_LAB_EXPERIMENTS_COLLECTION]


def ensure_retrieval_lab_indexes(client) -> None:
    """Create indexes for retrieval_lab_experiments."""
    coll = get_retrieval_lab_experiments_collection(client)
    coll.create_index([("experiment_id", 1)], unique=True)
    coll.create_index([("created_at", -1)])
    coll.create_index([("experiment_name", 1)])


def save_experiment(document: Dict[str, Any], mongo_uri: Optional[str] = None) -> str:
    """
    Persist an experiment document to retrieval_lab_experiments.
    document should contain experiment_id, experiment_name, created_at, config, results, etc.
    Returns the experiment_id.
    """
    client = _get_mongo_client(mongo_uri)
    ensure_retrieval_lab_indexes(client)
    coll = get_retrieval_lab_experiments_collection(client)
    payload = dict(document)
    payload.setdefault("created_at", datetime.now(timezone.utc))
    exp_id = payload.get("experiment_id")
    if not exp_id:
        raise ValueError("document must contain experiment_id")
    # Serialize any non-BSON types for MongoDB (e.g. convert datetime if already set)
    result = coll.replace_one(
        {"experiment_id": exp_id},
        payload,
        upsert=True,
    )
    return exp_id


def fetch_experiment(experiment_id: str, mongo_uri: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load a single experiment by experiment_id."""
    client = _get_mongo_client(mongo_uri)
    coll = get_retrieval_lab_experiments_collection(client)
    doc = coll.find_one({"experiment_id": experiment_id})
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


def list_experiments(
    limit: int = 50,
    mongo_uri: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List recent experiments (newest first)."""
    client = _get_mongo_client(mongo_uri)
    coll = get_retrieval_lab_experiments_collection(client)
    cursor = coll.find({}, {"experiment_id": 1, "experiment_name": 1, "created_at": 1}).sort(
        "created_at", -1
    ).limit(limit)
    return [{"_id": d.pop("_id", None), **d} for d in cursor]


def _sanitize_version(version: str) -> str:
    """Allow alphanumeric, underscore, hyphen for run_id segment."""
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in version).strip("_") or "v"


def substrate_run_id(
    document_id: str,
    corpus_unit_ids: List[str],
    substrate_version: Optional[str] = None,
) -> str:
    """
    Build a stable run_id for embedding cache.
    - If substrate_version is set: retrieval_lab_{document_id}_{substrate_version}.
      Re-embed only when you change extraction and bump the version.
    - Otherwise: retrieval_lab_{document_id}_{content_hash}.
      Same corpus (same sorted unit_ids) produces the same run_id.
    """
    if substrate_version and substrate_version.strip():
        ver = _sanitize_version(substrate_version.strip())
        return f"retrieval_lab_{document_id}_{ver}"
    content = "|".join(sorted(corpus_unit_ids))
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    return f"retrieval_lab_{document_id}_{h}"


def fetch_cached_embeddings(
    run_id: str,
    model_id: str,
    mongo_uri: Optional[str] = None,
):
    """
    Fetch chunk embeddings from MongoDB (reuses benchmark_store when available).
    Returns list of dicts with chunk_id, embedding, or None if not available or MongoDB unreachable.
    """
    try:
        from ruleslawyer.benchmark_store import fetch_chunk_embeddings
        return fetch_chunk_embeddings(run_id, model_id, mongo_uri)
    except ImportError:
        logger.warning("DungeonMindServer not on path; cannot use benchmark_store for embedding cache.")
        return None
    except Exception as e:  # e.g. ServerSelectionTimeoutError when MongoDB is down
        logger.warning("Could not fetch embedding cache (MongoDB unreachable?): %s", e)
        return None


def save_cached_embeddings(
    run_id: str,
    model_id: str,
    records: List[Dict[str, Any]],
    mongo_uri: Optional[str] = None,
    clear_existing: bool = True,
) -> int:
    """
    Save chunk embeddings to MongoDB via benchmark_store when available.
    records: list of {chunk_id, embedding, ...}.
    Returns number of documents inserted.
    """
    try:
        from ruleslawyer.benchmark_store import save_chunk_embeddings
        return save_chunk_embeddings(
            records,
            mongo_uri=mongo_uri,
            clear_existing=clear_existing,
            run_id=run_id,
            model_id=model_id,
        )
    except ImportError:
        logger.warning("DungeonMindServer not on path; skipping MongoDB embedding save.")
        return 0
    except Exception as e:
        logger.warning("Could not save embeddings to MongoDB: %s", e)
        return 0


def save_embedding_run_metadata(
    run_id: str,
    model_id: str,
    unit_count: int,
    mongo_uri: Optional[str] = None,
) -> None:
    """Record embedding run metadata in embedding_runs (via benchmark_store when available)."""
    try:
        from ruleslawyer.benchmark_store import save_embedding_run
        save_embedding_run(
            {
                "run_id": run_id,
                "model_id": model_id,
                "unit_count": unit_count,
                "source": "retrieval_lab",
            },
            mongo_uri=mongo_uri,
        )
    except (ImportError, Exception):
        pass
