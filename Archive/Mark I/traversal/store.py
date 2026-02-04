"""
MongoDB storage for TraversalConfig.

Stores traversal configurations per ruleset with versioning.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List

try:
    from pymongo import MongoClient
    from pymongo.collection import Collection
except ImportError as exc:
    raise RuntimeError("pymongo is required for MongoDB persistence.") from exc

from .config import TraversalConfig


DEFAULT_DB_NAME = "rules_ingestion"
TRAVERSAL_CONFIGS_COLLECTION = "traversal_configs"
TRAVERSAL_INDEXES_COLLECTION = "traversal_indexes"


def get_mongo_client(mongo_uri: str) -> MongoClient:
    """Get MongoDB client."""
    return MongoClient(mongo_uri)


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


def ensure_traversal_indexes(client: MongoClient, db_name: str = DEFAULT_DB_NAME) -> None:
    """Ensure indexes exist for traversal collections."""
    # Traversal configs: unique by ruleset_id + version
    get_traversal_configs_collection(client, db_name).create_index(
        [("ruleset_id", 1), ("version", -1)], unique=True
    )
    get_traversal_configs_collection(client, db_name).create_index(
        [("ruleset_id", 1), ("updated_at", -1)]
    )
    
    # Traversal indexes: unique by ruleset_id + book_id + run_id
    get_traversal_indexes_collection(client, db_name).create_index(
        [("ruleset_id", 1), ("book_id", 1), ("run_id", 1)], unique=True
    )
    get_traversal_indexes_collection(client, db_name).create_index(
        [("ruleset_id", 1), ("created_at", -1)]
    )


# ============================================================================
# TraversalConfig Storage
# ============================================================================

def save_traversal_config(
    config: TraversalConfig,
    mongo_uri: str,
    version: str = "v1",
    db_name: str = DEFAULT_DB_NAME,
) -> str:
    """
    Save TraversalConfig to MongoDB.
    
    Args:
        config: TraversalConfig to save
        mongo_uri: MongoDB connection URI
        version: Version string for the config
        db_name: Database name
        
    Returns:
        Inserted/updated document ID as string
    """
    client = get_mongo_client(mongo_uri)
    collection = get_traversal_configs_collection(client, db_name)
    
    # Build document
    payload = config.to_dict()
    payload["version"] = version
    now = datetime.now(timezone.utc)
    payload["updated_at"] = now
    payload.setdefault("created_at", now)
    
    # Upsert by ruleset_id + version
    result = collection.replace_one(
        {"ruleset_id": config.ruleset_id, "version": version},
        payload,
        upsert=True,
    )
    
    if result.upserted_id:
        return str(result.upserted_id)
    
    doc = collection.find_one(
        {"ruleset_id": config.ruleset_id, "version": version}
    )
    return str(doc.get("_id")) if doc else ""


def fetch_traversal_config(
    ruleset_id: str,
    mongo_uri: str,
    version: Optional[str] = None,
    db_name: str = DEFAULT_DB_NAME,
) -> Optional[TraversalConfig]:
    """
    Fetch TraversalConfig from MongoDB.
    
    Args:
        ruleset_id: Ruleset identifier
        mongo_uri: MongoDB connection URI
        version: Specific version to fetch (None = latest)
        db_name: Database name
        
    Returns:
        TraversalConfig or None if not found
    """
    client = get_mongo_client(mongo_uri)
    collection = get_traversal_configs_collection(client, db_name)
    
    if version:
        doc = collection.find_one({"ruleset_id": ruleset_id, "version": version})
    else:
        # Fetch latest by updated_at
        doc = collection.find_one(
            {"ruleset_id": ruleset_id},
            sort=[("updated_at", -1)],
        )
    
    if not doc:
        return None
    
    # Remove MongoDB fields
    doc.pop("_id", None)
    doc.pop("version", None)
    doc.pop("created_at", None)
    doc.pop("updated_at", None)
    
    return TraversalConfig(
        ruleset_id=doc.get("ruleset_id", "generic"),
        condition_names=set(doc.get("condition_names", [])),
        spell_names=set(doc.get("spell_names", [])),
        feat_names=set(doc.get("feat_names", [])),
        item_names=set(doc.get("item_names", [])),
        action_names=set(doc.get("action_names", [])),
        player_keywords=set(doc.get("player_keywords", [])),
        gm_keywords=set(doc.get("gm_keywords", [])),
        intent_patterns=doc.get("intent_patterns", {}),
        policies=doc.get("policies", {}),
    )


def list_traversal_config_versions(
    ruleset_id: str,
    mongo_uri: str,
    db_name: str = DEFAULT_DB_NAME,
) -> List[dict]:
    """
    List all versions of TraversalConfig for a ruleset.
    
    Returns list of {version, updated_at, game_term_count} dicts.
    """
    client = get_mongo_client(mongo_uri)
    collection = get_traversal_configs_collection(client, db_name)
    
    cursor = collection.find(
        {"ruleset_id": ruleset_id},
        projection={
            "version": 1,
            "updated_at": 1,
            "condition_names": 1,
            "spell_names": 1,
            "feat_names": 1,
        },
        sort=[("updated_at", -1)],
    )
    
    versions = []
    for doc in cursor:
        game_term_count = (
            len(doc.get("condition_names", [])) +
            len(doc.get("spell_names", [])) +
            len(doc.get("feat_names", []))
        )
        versions.append({
            "version": doc.get("version"),
            "updated_at": doc.get("updated_at"),
            "game_term_count": game_term_count,
        })
    
    return versions


# ============================================================================
# TraversalIndex Storage (sparse - only store lookups, not full chunks)
# ============================================================================

def save_traversal_index_metadata(
    ruleset_id: str,
    book_id: str,
    run_id: str,
    index_stats: dict,
    mongo_uri: str,
    db_name: str = DEFAULT_DB_NAME,
) -> str:
    """
    Save TraversalIndex metadata to MongoDB.
    
    Note: We don't store the full index (term_to_chunks etc) in MongoDB
    as it's very large. Instead store metadata and rebuild from graph/chunks.
    
    Args:
        ruleset_id: Ruleset identifier
        book_id: Book identifier
        run_id: Run identifier
        index_stats: Stats about the index (total_chunks, total_edges, etc.)
        mongo_uri: MongoDB connection URI
        db_name: Database name
        
    Returns:
        Inserted/updated document ID
    """
    client = get_mongo_client(mongo_uri)
    collection = get_traversal_indexes_collection(client, db_name)
    
    now = datetime.now(timezone.utc)
    payload = {
        "ruleset_id": ruleset_id,
        "book_id": book_id,
        "run_id": run_id,
        "stats": index_stats,
        "created_at": now,
    }
    
    result = collection.replace_one(
        {"ruleset_id": ruleset_id, "book_id": book_id, "run_id": run_id},
        payload,
        upsert=True,
    )
    
    if result.upserted_id:
        return str(result.upserted_id)
    
    doc = collection.find_one(
        {"ruleset_id": ruleset_id, "book_id": book_id, "run_id": run_id}
    )
    return str(doc.get("_id")) if doc else ""


def fetch_latest_traversal_index_metadata(
    ruleset_id: str,
    book_id: str,
    mongo_uri: str,
    db_name: str = DEFAULT_DB_NAME,
) -> Optional[dict]:
    """
    Fetch latest TraversalIndex metadata for a ruleset/book.
    
    Returns dict with run_id, stats, created_at or None.
    """
    client = get_mongo_client(mongo_uri)
    collection = get_traversal_indexes_collection(client, db_name)
    
    doc = collection.find_one(
        {"ruleset_id": ruleset_id, "book_id": book_id},
        sort=[("created_at", -1)],
    )
    
    if not doc:
        return None
    
    doc.pop("_id", None)
    return doc
