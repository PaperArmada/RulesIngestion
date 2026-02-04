"""Ruleset config persistence utilities."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Optional

from config_generator import RulesetConfiguration
from config_profile import RulesetProfile

try:
    from pymongo import MongoClient
    from pymongo.collection import Collection
except ImportError as exc:  # pragma: no cover - runtime dependency guard
    raise RuntimeError("pymongo is required for MongoDB persistence helpers.") from exc


DEFAULT_DB_NAME = "rules_ingestion"
RULESET_CONFIGS_COLLECTION = "ruleset_configs"
RULESET_PROFILES_COLLECTION = "ruleset_profiles"
ENRICHMENT_RUNS_COLLECTION = "enrichment_runs"
RUN_INPUTS_COLLECTION = "run_inputs"
RUN_OUTPUTS_COLLECTION = "run_outputs"
TRAVERSAL_CONFIGS_COLLECTION = "traversal_configs"
TRAVERSAL_INDEXES_COLLECTION = "traversal_indexes"


def _model_dump(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _parse_version_number(version: str) -> Optional[int]:
    match = re.search(r"(\d+)$", version)
    if not match:
        return None
    return int(match.group(1))


def get_mongo_client(mongo_uri: str) -> MongoClient:
    return MongoClient(mongo_uri)


def get_ruleset_configs_collection(
    client: MongoClient, db_name: str = DEFAULT_DB_NAME
) -> Collection:
    return client[db_name][RULESET_CONFIGS_COLLECTION]


def get_ruleset_profiles_collection(
    client: MongoClient, db_name: str = DEFAULT_DB_NAME
) -> Collection:
    return client[db_name][RULESET_PROFILES_COLLECTION]


def get_enrichment_runs_collection(
    client: MongoClient, db_name: str = DEFAULT_DB_NAME
) -> Collection:
    return client[db_name][ENRICHMENT_RUNS_COLLECTION]


def get_run_inputs_collection(
    client: MongoClient, db_name: str = DEFAULT_DB_NAME
) -> Collection:
    return client[db_name][RUN_INPUTS_COLLECTION]


def get_run_outputs_collection(
    client: MongoClient, db_name: str = DEFAULT_DB_NAME
) -> Collection:
    return client[db_name][RUN_OUTPUTS_COLLECTION]


def get_traversal_configs_collection(
    client: MongoClient, db_name: str = DEFAULT_DB_NAME
) -> Collection:
    """Get traversal_configs collection."""
    return client[db_name][TRAVERSAL_CONFIGS_COLLECTION]


def get_traversal_indexes_collection(
    client: MongoClient, db_name: str = DEFAULT_DB_NAME
) -> Collection:
    """Get traversal_indexes collection."""
    return client[db_name][TRAVERSAL_INDEXES_COLLECTION]


def ensure_indexes(client: MongoClient, db_name: str = DEFAULT_DB_NAME) -> None:
    """Ensure baseline indexes exist for rules ingestion collections."""
    get_ruleset_configs_collection(client, db_name).create_index(
        [("ruleset_id", 1), ("version", -1)], unique=True
    )
    get_ruleset_configs_collection(client, db_name).create_index(
        [("ruleset_id", 1), ("version_number", -1)]
    )
    get_ruleset_configs_collection(client, db_name).create_index(
        [("source_fingerprint", 1)]
    )
    get_ruleset_profiles_collection(client, db_name).create_index([("ruleset_id", 1)])
    get_enrichment_runs_collection(client, db_name).create_index([("ruleset_id", 1)])
    get_enrichment_runs_collection(client, db_name).create_index([("config_version", 1)])
    get_enrichment_runs_collection(client, db_name).create_index([("status", 1)])
    get_enrichment_runs_collection(client, db_name).create_index([("started_at", -1)])
    get_run_inputs_collection(client, db_name).create_index([("run_id", 1)])
    get_run_outputs_collection(client, db_name).create_index([("run_id", 1)])
    
    # Traversal config indexes
    get_traversal_configs_collection(client, db_name).create_index(
        [("ruleset_id", 1), ("version", -1)], unique=True
    )
    get_traversal_configs_collection(client, db_name).create_index(
        [("ruleset_id", 1), ("updated_at", -1)]
    )
    
    # Traversal index metadata indexes
    get_traversal_indexes_collection(client, db_name).create_index(
        [("ruleset_id", 1), ("book_id", 1), ("run_id", 1)], unique=True
    )
    get_traversal_indexes_collection(client, db_name).create_index(
        [("ruleset_id", 1), ("created_at", -1)]
    )


def save_ruleset_profile(
    profile: RulesetProfile, mongo_uri: str, db_name: str = DEFAULT_DB_NAME
) -> str:
    client = get_mongo_client(mongo_uri)
    collection = get_ruleset_profiles_collection(client, db_name)
    payload = _model_dump(profile)
    result = collection.insert_one(payload)
    return str(result.inserted_id)


def fetch_latest_ruleset_profile(
    ruleset_id: str, mongo_uri: str, db_name: str = DEFAULT_DB_NAME
) -> Optional[RulesetProfile]:
    client = get_mongo_client(mongo_uri)
    collection = get_ruleset_profiles_collection(client, db_name)
    doc = collection.find_one({"ruleset_id": ruleset_id}, sort=[("created_at", -1)])
    if not doc:
        return None
    doc.pop("_id", None)
    return RulesetProfile(**doc)


def save_ruleset_config(
    config: RulesetConfiguration, mongo_uri: str, db_name: str = DEFAULT_DB_NAME
) -> str:
    client = get_mongo_client(mongo_uri)
    collection = get_ruleset_configs_collection(client, db_name)
    payload = _model_dump(config)
    payload["version_number"] = _parse_version_number(payload["version"])
    now = datetime.now(timezone.utc)
    payload["updated_at"] = now
    payload.setdefault("created_at", now)
    result = collection.replace_one(
        {"ruleset_id": payload["ruleset_id"], "version": payload["version"]},
        payload,
        upsert=True,
    )
    if result.upserted_id:
        return str(result.upserted_id)
    doc = collection.find_one(
        {"ruleset_id": payload["ruleset_id"], "version": payload["version"]}
    )
    return str(doc.get("_id")) if doc else ""


def fetch_latest_ruleset_config(
    ruleset_id: str, mongo_uri: str, db_name: str = DEFAULT_DB_NAME
) -> Optional[RulesetConfiguration]:
    client = get_mongo_client(mongo_uri)
    collection = get_ruleset_configs_collection(client, db_name)
    doc = collection.find_one(
        {"ruleset_id": ruleset_id},
        sort=[("version_number", -1), ("updated_at", -1)],
    )
    if not doc:
        return None
    doc.pop("_id", None)
    return RulesetConfiguration(**doc)


def fetch_ruleset_config_by_version(
    ruleset_id: str,
    version: str,
    mongo_uri: str,
    db_name: str = DEFAULT_DB_NAME,
) -> Optional[RulesetConfiguration]:
    client = get_mongo_client(mongo_uri)
    collection = get_ruleset_configs_collection(client, db_name)
    doc = collection.find_one({"ruleset_id": ruleset_id, "version": version})
    if not doc:
        return None
    doc.pop("_id", None)
    return RulesetConfiguration(**doc)
