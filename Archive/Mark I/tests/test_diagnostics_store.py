from datetime import datetime, timezone

from diagnostics_store import (
    DiagnosticsRetentionPolicy,
    GenerationDiagnostics,
    apply_retention_policy,
    save_generation_diagnostics,
)


def test_generation_diagnostics_shape_and_retention() -> None:
    diagnostics = GenerationDiagnostics(
        ruleset_id="sf2e",
        doc_signature="sig",
        attempt_number=3,
        validation_errors=["missing version"],
    )
    policy = DiagnosticsRetentionPolicy(retention_days=7)
    updated = apply_retention_policy(diagnostics, policy)

    assert updated.ruleset_id == "sf2e"
    assert updated.validation_errors == ["missing version"]
    assert updated.expires_at is not None
    assert updated.expires_at > updated.created_at


def test_diagnostics_persistence(monkeypatch) -> None:
    class FakeCollection:
        def __init__(self) -> None:
            self.inserted = []

        def insert_one(self, payload):
            self.inserted.append(payload)
            return type("Result", (), {"inserted_id": "fake-id"})

    class FakeDb:
        def __init__(self, collection) -> None:
            self.collection = collection

        def __getitem__(self, name):
            if name == "ruleset_config_diagnostics":
                return self.collection
            raise KeyError(name)

    class FakeClient:
        def __init__(self, collection) -> None:
            self.collection = collection

        def __getitem__(self, name):
            return FakeDb(self.collection)

    collection = FakeCollection()

    def fake_client(_uri: str):
        return FakeClient(collection)

    monkeypatch.setattr("diagnostics_store.get_mongo_client", fake_client)

    diagnostics = GenerationDiagnostics(
        ruleset_id="sf2e",
        doc_signature="sig",
        attempt_number=1,
        validation_errors=["invalid"],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    record_id = save_generation_diagnostics(diagnostics, mongo_uri="mongodb://localhost")

    assert record_id == "fake-id"
    assert len(collection.inserted) == 1
    assert collection.inserted[0]["expires_at"] is not None
