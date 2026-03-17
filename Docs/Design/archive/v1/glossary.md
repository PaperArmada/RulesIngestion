# Glossary v1

**EvidenceUnit** — Canonical admissible unit of evidence emitted by Stage B. One prose block, table, or list with stable identity and provenance. The only layer that may be cited as evidence.

**Projection** — A retrieval-only view derived from EvidenceUnits (e.g. clause family, context window, graph-expanded unit). Not admissible; never cited.

**Candidate** — A unit (EvidenceUnit or projection) that appears in a retrieval result list. May carry source_list and merge_reason (e.g. dual_list, pairing).

**Gold** — The set of EvidenceUnit IDs that are considered relevant for a query (ground truth for eval). Manually grounded (Baseline-A) or semantically grounded with explicit documentation.

**Full-set** — For a query with multiple gold units, the condition that all gold units appear in the top-k. Full-set Hit@k = fraction of queries where all gold are in top-k.

**structural_path** — List of heading labels from document root to the unit (heading ancestry). Empty for orphans unless assigned by Orphan Header Pass.

**anchor unit** — In clause-family projection: the EvidenceUnit that is the anchor of a family (e.g. the unit that matched the query); members are nearby units by structural_path and order.

**family window** — Parameter: how many heading levels or steps to include around the anchor when building a clause family.

**max units** — Parameter: maximum number of units in a clause family (cap).

**T1 / T2 / T3** — Query tiers. T1: single gold unit (or primary unit); T2/T3: multi-unit or compositional. Used for stratified metrics and T1 regression policy.

**admissible** — Authoritative, citable evidence. Only EvidenceUnits are admissible. Enrichment and projections are non-authoritative.

**non-authoritative** — Not evidence; used only for retrieval (e.g. A′ enrichment, clause families). Tagged so they are never cited.
