# **Architectural Frontiers in Tabletop Role-Playing Game Information Retrieval: A Deep Research Report on Multimodal RAG and Symbolic Logic Integration**

The technical challenge of achieving impeccable retrieval from Tabletop Role-Playing Game (TTRPG) rulebooks represents a unique intersection of document intelligence, semantic engineering, and symbolic reasoning. Unlike standard corporate corpora, TTRPG rulebooks are Visually Structured Documents (VSDs) that rely on complex multi-column layouts, hierarchical headers, interleaved tables, and dense cross-references where the mechanical meaning of a term often diverges sharply from its natural language usage.1 A word such as "Prone" denotes a physical state in general English, but in a TTRPG context, it functions as a discrete status effect with associated numerical penalties, triggers, and interactions with other conditions.3 Consequently, the design of a high-fidelity retrieval system for this domain requires moving beyond the limitations of "vanilla" Retrieval-Augmented Generation (RAG) toward a multimodal, ontologically grounded framework capable of both semantic understanding and symbolic rule arbitration.6

## **The Ingestion Bottleneck: Multimodal Parsing and Visual Document Understanding**

The foundational stage of any RAG pipeline is the extraction of high-quality, structured data from raw source materials. For TTRPG rulebooks, the primary source is typically the PDF format, which presents significant obstacles to traditional text extraction.1 These documents feature non-linear text storage, where the underlying code may not match the visual order on the page, and intricate layouts that standard parsers frequently jumble into nonsensical text strings.2 When a parser reads across the page instead of respecting column boundaries, the resulting "garbage in, garbage out" effect destroys the semantic utility of the embedding models that follow.1

### **Comparative Evaluation of Ingestion Methodologies**

A rigorous critique of current design choices must begin with the parsing strategy. Naive text extraction, which simply scrapes strings, is demonstrably inadequate for rulebooks where reading order is defined by visual layout rather than character flow.1 Advanced solutions fall into three main categories: rule-based, layout-aware, and vision-guided.

| Parsing Strategy | Primary Mechanism | Domain Advantages | Critical Failure Modes |
| :---- | :---- | :---- | :---- |
| **Rule-Based (e.g., Unstructured)** | Detects bounding boxes and classifies elements using heuristics.1 | High speed; provides metadata like page numbers and element types.1 | Struggles with non-standard artistic fonts and overlapping graphical elements.2 |
| **Layout-Aware (e.g., LayoutPDFReader)** | Context-aware chunking that links paragraphs to section headers.2 | Maintains hierarchy; recognizes tables and nested list structures.2 | Dependent on a clean text layer; lacks native OCR for scanned legacy rulebooks.2 |
| **Vision-Guided (LMM-Based)** | Employs Large Multimodal Models to process page images and text simultaneously.11 | Preserves semantic coherence across page boundaries; handles complex multi-page tables.9 | Significant computational cost; requires batching to manage context windows.11 |

The most robust design choice for impeccable retrieval is the vision-guided framework. Recent research indicates that vision-guided RAG achieves 0.89 accuracy compared to 0.78 for vanilla systems, a 14% relative improvement.11 This framework processes documents in configurable page batches, typically four pages at a time, with cross-batch context preservation to ensure that rules spanning multiple pages remain coherent.11 This approach allows the system to enforce critical content preservation rules: numbered steps in a procedure remain together, and table rows maintain their essential relationship with headers.9

### **Hierarchical Transformation and Metadata Enrichment**

Following successful parsing, the data must be transformed into a format that supports explainable retrieval. This involves mapping extracted elements (Titles, NarrativeText, ListItem, Table) into a structured document object while preserving metadata such as page numbers and section hierarchy.1 For TTRPGs, this metadata acts as a retrieval anchor, allowing the system to return citations that lead players directly to the relevant physical book page.1  
Metadata architecture is often undervalued in prototype systems but accounts for approximately 40% of development time in production-grade environments.14 In the TTRPG context, essential metadata fields include the source book (e.g., "Player's Handbook"), the content category (e.g., "Spell," "Combat Action," "Monster Trait"), and the hierarchical lineage of the chunk.6 This ensures that when a specific rule about "Opportunity Attacks" is retrieved, the LLM also receives context about "Movement" and "Reaction" economies, which are necessary for a complete and accurate mechanical response.15

## **Chunking Strategies: Preserving Mechanical Coherence**

Chunking is the process of segmenting a document into units that are small enough for precise retrieval but large enough to retain meaningful context.2 Traditional fixed-size chunking—splitting text every 512 tokens, for example—is destructive in the rules domain because it frequently breaks sentences mid-thought and separates rules from their essential situational qualifiers.17

### **The Limitations of Semantic and Recursive Chunking**

While semantic chunking—grouping text based on the similarity of sentence embeddings—is superior to fixed-size methods, it still fails to capture the visual and structural elements integral to rulebook understanding.9 Semantic similarity does not always equate to mechanical relevance; two sections might be semantically similar because they describe "fire damage," but one is a spell and the other is an environmental hazard.19  
Recursive chunking, which splits at natural document boundaries (paragraphs, then newlines, then sentences), works better for hierarchical structures like rulebooks but remains limited by "chunking drift".17 Boundary drift occurs when minor formatting changes between rulebook versions cause chunk boundaries to shift, breaking previously stable embeddings and leading to inconsistent retrieval results.22

### **Advanced Solutions: Parent-Child Retrieval and Vision-Guided Consistency**

To mitigate context dilution and fragmentation, a "Parent Document" retrieval strategy is highly recommended.6 In this architecture, documents are dissected into small "child" chunks that capture specific thematic essence for precise retrieval.6 However, during the generation phase, the system does not merely send the child chunk to the LLM; instead, it retrieves the larger "parent" block—such as an entire section or sub-chapter—to provide a thorough context.6 This twofold advantage allows for the specificity of child embeddings while ensuring the LLM's outputs are grounded in a layered, thorough context.16  
The implementation of vision-guided chunking further refines this by enforcing "Inseparability Rules" 9:

* Numbered steps, instructions, or procedures must never be split across different chunks.9  
* All items in a list must stay together in a single chunk, even if they span across multiple images or page breaks.9  
* Multi-page tables must maintain header-row relationships across chunks.2

This strategy produces approximately five times more chunks than traditional methods, indicating a much higher granularity of segmentation that translates directly into better downstream performance.11

## **Hybrid Retrieval: Balancing Semantic Intent with Token Precision**

A rigorous critique of TTRPG retrieval must acknowledge that semantic vector search alone is insufficient for rules systems.6 Vector search excels at understanding intent—for instance, matching "how do I hurt a ghost" to documents about "Necrotic Damage" and "Ethereal Entities"—but often misses exact tokens, acronyms, and rare strings such as "DC 15 Dexterity Saving Throw".6

### **Lexical Precision via BM25**

In the gaming domain, exact keyword matching is critical. Traditional lexical search algorithms like BM25 (Best Matching 25\) solve this by evaluating relevance based on term frequency, inverse document frequency (prioritizing rare terms like "Smiting"), and document length normalization.23  
The mathematical representation of BM25 highlights its focus on discriminative terms:

$$\\text{score}(D, Q) \= \\sum\_{q \\in Q} \\text{IDF}(q) \\cdot \\frac{f(q, D) \\cdot (k\_1 \+ 1)}{f(q, D) \+ k\_1 \\cdot (1 \- b \+ b \\cdot \\frac{|D|}{\\text{avgdl}})}$$  
where $f(q, D)$ is the frequency of query term $q$ in document $D$, $|D|$ is the length of document $D$, and $\\text{avgdl}$ is the average document length.26 This ensures that shorter, focused paragraphs about specific rules are prioritized over 50-page manuals that only mention a term in passing.23

### **Fusion and Re-ranking**

The optimal design choice for TTRPG retrieval is a hybrid approach that pairs BM25 with dense vector search using Reciprocal Rank Fusion (RRF).23 RRF is robust because it is scale-independent; it does not care if BM25 scores range from 0–1000 and vector similarities from 0–1; it only considers the relative rankings in each list.23

$$\\text{RRFScore}(d) \= \\sum\_{r \\in R} \\frac{1}{k \+ r(d)}$$  
where $R$ is the set of retrieval rankings and $k$ is a constant, usually 60\.26  
Following initial hybrid retrieval, a re-ranking stage is necessary to ensure the highest-quality context reaches the LLM.27 Re-ranking with models such as Cohere Rerank or cross-encoders can boost accuracy by over 11 percentage points by prioritizing context that is not just semantically similar, but truly relevant to the mechanical answer.28

## **Symbolic Logic: Knowledge Graphs and the Rule of Law**

While hybrid RAG is effective for local rule lookups, it struggles with complex multi-hop relationships and global cross-document themes.6 For example, determining the total damage of a "Critical Hit with a Flame Tongue Longsword for a Paladin using Divine Smite against an Undead target" requires pulling information from character traits, item properties, spell descriptions, and creature type vulnerabilities.8

### **Transitioning to GraphRAG**

Knowledge Graphs (KGs) represent information as nodes (entities like "Paladin" or "Fire Damage") and edges (relationships like "HasClass" or "ResistantTo").8 Integrating a KG into the retrieval pipeline—known as GraphRAG—enables the system to reason over interconnected knowledge rather than isolated text snippets.8 Unlike flat vector databases, KGs preserve hierarchies and causal chains.8

| Retrieval Component | Traditional Vector RAG | Graph-Enhanced RAG (GraphRAG) |
| :---- | :---- | :---- |
| **Data Representation** | Unstructured text chunks.30 | Entities, relationships, and ontologies.8 |
| **Search Mechanism** | Vector similarity (semantic).23 | Graph traversal and multi-hop pathfinding.8 |
| **Reasoning Type** | Probabilistic/Pattern-based.32 | Symbolic/Relational reasoning.8 |
| **Explainability** | Low (semantic proximity).6 | High (traceable graph paths).8 |

### **The Necessity of Formal Ontologies**

A critical design refinement is the implementation of a formal ontology (OWL/RDF) to ground the knowledge graph.33 Without an ontology, a graph database is merely a collection of fancy labels; with an ontology, the system can perform machine-readable inference.34 For TTRPGs, the ontology defines the vocabulary and the structure of the information, such as defining that "Beholder" is a subclass of "Aberration," and all "Aberrations" might share certain mechanical resistances.31  
This solves the "Jaguar Problem"—disambiguating between the car, the animal, and the guitar—by assigning entities to specific semantic classes defined in the ontology.34 In a TTRPG system, this disambiguation is crucial for resolving conflicts between "Flavor Text" (descriptive) and "Mechanical Text" (rule-bound).15

## **Modeling the Mechanical Engine: Event-Driven Architectures**

To reach the pinnacle of TTRPG retrieval—what we might call "executable RAG"—the system must model the rules as a logical engine rather than just a searchable text corpus.5 This requires an event-driven architecture where game mechanics are represented as interacting subsystems.5

### **Event Phases and Modification Channels**

Mechanical rules in modern TTRPGs (like D\&D 5e) follow a distinct action flow 5:

1. **Declaration:** The initial intent (e.g., "I attack").  
2. **Prerequisites:** Checking if the action can be performed (e.g., ammunition, range).  
3. **Execution:** Rolling dice and determining success or failure.5  
4. **Effect:** Applying consequences (e.g., damage, conditions).  
5. **Completion:** Finalizing the state change.

Retrieval systems can be refined by modeling these as Directed Acyclic Graphs (DAGs), where each conditional rule is a vertex and the resulting effects are edges.5 A character's values (like Armor Class) are then managed through four distinct modification channels: self\_static, self\_contextual, to\_target\_static, and to\_target\_contextual.5 This allows the retrieval system to account for situational modifiers—such as "Cover" or "Advantage"—that are not part of the static rule but emerge from the current game state.5

### **Integrating with VTT Data Models**

A rigorous design must also ensure that retrieved rules are compatible with the data structures used by Virtual Tabletops (VTTs). For example, Foundry VTT has shifted from static template.json structures to dynamic DataModel classes.38 These models synchronize information between client and server, providing functions for cleaning, validating, and migrating data.38  
By outputting retrieved rules in a format that matches these TypeDataModel schemas, a RAG system can move beyond answering questions to actually updating the game state.38 This involves distinguishing between the \_source (the raw database-friendly data) and the initialized properties (the active game values).38

## **Domain-Specific Entity Intelligence: Fine-Tuning for Fantasy**

General-purpose Named Entity Recognition (NER) models are fundamentally mismatched for the fantasy domain.3 While a standard BERT model can identify "Apple Inc." or "Tim Cook," it achieves a 0.00% F1 score when trying to identify monster names like "Lich" or "Beholder".4

### **Custom NER Frameworks**

Impeccable retrieval requires fine-tuning NER models on a domain-relevant corpus, such as the System Reference Document (SRD) or lore from D\&D Beyond.3 Frameworks like Trankit (using XLM-Roberta) or FLAIR (using BiLSTM-CRF) have been shown to achieve F1 scores of approximately 87% for fantasy monster names.3

| NER Model | Base Architecture | Fantasy F1 Score | Key Strength |
| :---- | :---- | :---- | :---- |
| **Trankit** | XLM-Roberta-base | 87.86%.4 | High precision; identifies untagged monsters through context.4 |
| **FLAIR Config 2** | BiLSTM-CRF | 87.43%.4 | Superior recall; effective even with smaller training datasets.4 |

This specialized entity extraction is the foundation for "Pseudo-Knowledge Graphs" (PKG), which integrate natural language text preservation with meta-path retrieval to provide a context-aware retrieval system that is far more accurate than generic vector similarity.45

## **Benchmarking the Impossible: Metrics for Rule Accuracy**

Evaluating a TTRPG retrieval system requires established "gold standard" datasets early in the lifecycle.46 These are predefined question-and-answer pairs that represent the ground truth of the system.29

### **Core Evaluation Metrics**

The "RAG Triad"—evaluating the relationship between the Query, the Context, and the Response—provides a comprehensive view of performance.48

| Metric | Measurement Goal | TTRPG Significance |
| :---- | :---- | :---- |
| **Context Relevance** | Is the retrieved chunk actually helpful? | Filtering out "Flavor Text" in favor of "Mechanical Rules".47 |
| **Faithfulness** | Does the answer stick to the source text? | Preventing "Hallucinations" of homebrew or incorrect rules.46 |
| **MRR@10** | Is the correct rule ranked at the top? | Critical for game-time lookups where speed is paramount.28 |
| **Context Sufficiency** | Is all the info needed to answer present? | Essential for multi-part questions like "Spellcasting under Water".46 |

Benchmarking information retrieval (BeIR) across specialized domains like TTRPGs ensures that the models do not just guess but provide accurate, traceable results.46 Systems such as RAGAS can then automate these evaluations by measuring semantic similarity and context entity recall.51

## **Synthesis and Design Critique: Towards a Unified Retrieval Architecture**

The pursuit of impeccable TTRPG retrieval necessitates an architectural synthesis that rejects naive "text-to-embedding" pipelines in favor of a multimodal, multi-layered framework.

### **The Refined Pipeline Strategy**

1. **Vision-Guided Ingestion:** Rulebooks must be parsed using multimodal models (LMMs) to preserve the hierarchical, multi-column, and tabular structure of the source.2  
2. **Parent-Child Hierarchical Chunking:** Use small child chunks for precise retrieval and larger parent documents for generation context to maintain semantic coherence.6  
3. **Hybrid RRF Search:** Parallel BM25 lexical search and dense vector search, fused via Reciprocal Rank Fusion, to balance semantic intent with keyword precision (e.g., for DCs and saving throws).23  
4. **Ontological GraphRAG:** Grounding retrieval in a formal RDF/OWL ontology to support multi-hop reasoning over character classes, items, and conditions.8  
5. **Re-ranking and Contextual Compression:** Utilizing cross-encoders to prioritize retrieved context and removing irrelevant noise before sending the prompt to the generator.16  
6. **Agentic Execution:** Integrating with VTT Data Models to ensure that the retrieved rule is not just displayed as text but is ready for mechanical execution within the virtual environment.38

### **Rigorous Critique of Design Trade-offs**

The most common failure in personal TTRPG RAG projects is the over-reliance on vector similarity.6 While vector search feels "magical" during simple queries, it fails the "Rules of Law" test. In a rules environment, "Near Similarity" is often a failure. If a player asks about "Resistance to Fire," a vector search might return a section on "Immunity to Fire" because they are semantically close, but mechanically they are vastly different.23 Therefore, the inclusion of a lexical search layer (BM25) and a symbolic reasoning layer (Knowledge Graphs) is not optional—it is the prerequisite for "Impeccable Retrieval."  
Furthermore, the "Vision-Guided" approach is the only sustainable way to handle the artistic complexity of high-end RPG books. Without it, the ingestion pipeline remains the single greatest point of failure, consistently feeding jumbled or incomplete context into even the most advanced LLMs.1 By adopting these advanced refinements—vision-guided parsing, hybrid RRF search, and ontologically-grounded GraphRAG—the system can finally meet the demands of technical TTRPG play, providing answers that are accurate, explainable, and mechanically robust.

#### **Works cited**

1. Document Parsing for RAG: Handling Multi-Column Documents, accessed February 9, 2026, [https://www.omdena.com/blog/document-parsing-for-rag](https://www.omdena.com/blog/document-parsing-for-rag)  
2. PDF Parsing Guide: Extract Sections & Tables | LlamaIndex, accessed February 9, 2026, [https://www.llamaindex.ai/blog/mastering-pdfs-extracting-sections-headings-paragraphs-and-tables-with-cutting-edge-parser-faea18870125](https://www.llamaindex.ai/blog/mastering-pdfs-extracting-sections-headings-paragraphs-and-tables-with-cutting-edge-parser-faea18870125)  
3. Fine Tuning Named Entity Extraction Models for the Fantasy Domain \- arXiv, accessed February 9, 2026, [https://arxiv.org/pdf/2402.10662](https://arxiv.org/pdf/2402.10662)  
4. Fine Tuning Named Entity Extraction Models for the Fantasy ... \- arXiv, accessed February 9, 2026, [https://arxiv.org/abs/2402.10662](https://arxiv.org/abs/2402.10662)  
5. furlat/dnd\_engine: A python engine for playing dnd 5e \- GitHub, accessed February 9, 2026, [https://github.com/furlat/dnd\_engine](https://github.com/furlat/dnd_engine)  
6. Advanced RAG Techniques for High-Performance LLM Applications \- Graph Database & Analytics \- Neo4j, accessed February 9, 2026, [https://neo4j.com/blog/genai/advanced-rag-techniques/](https://neo4j.com/blog/genai/advanced-rag-techniques/)  
7. Advanced RAG: Techniques, Architecture, and Best Practices \- Designveloper, accessed February 9, 2026, [https://www.designveloper.com/blog/advanced-rag/](https://www.designveloper.com/blog/advanced-rag/)  
8. What Is GraphRAG Knowledge Graph? \- PuppyGraph, accessed February 9, 2026, [https://www.puppygraph.com/blog/graphrag-knowledge-graph](https://www.puppygraph.com/blog/graphrag-knowledge-graph)  
9. Vision-Guided Chunking Is All You Need: Enhancing RAG with Multimodal Document Understanding \- arXiv, accessed February 9, 2026, [https://arxiv.org/html/2506.16035v2](https://arxiv.org/html/2506.16035v2)  
10. What's the Best PDF Extractor for RAG? I Tried LlamaParse, Unstructured and Vectorize | by Pavan Belagatti | Level Up Coding, accessed February 9, 2026, [https://levelup.gitconnected.com/whats-the-best-pdf-extractor-for-rag-i-tried-llamaparse-unstructured-and-vectorize-4abbd57b06e0](https://levelup.gitconnected.com/whats-the-best-pdf-extractor-for-rag-i-tried-llamaparse-unstructured-and-vectorize-4abbd57b06e0)  
11. Vision-Guided Chunking Is All You Need: Enhancing RAG with Multimodal Document Understanding | alphaXiv, accessed February 9, 2026, [https://www.alphaxiv.org/overview/2506.16035v2](https://www.alphaxiv.org/overview/2506.16035v2)  
12. Vision-Guided Chunking Is All You Need: Enhancing RAG with Multimodal Document Understanding \- arXiv, accessed February 9, 2026, [https://arxiv.org/pdf/2506.16035](https://arxiv.org/pdf/2506.16035)  
13. Building a Multimodal LLM Application with PyMuPDF4LLM \- Artifex Software Inc., accessed February 9, 2026, [https://artifex.com/blog/building-a-multimodal-llm-application-with-pymupdf4llm](https://artifex.com/blog/building-a-multimodal-llm-application-with-pymupdf4llm)  
14. I Built RAG Systems for Enterprises (20K+ Docs). Here's the learning ..., accessed February 9, 2026, [https://www.reddit.com/r/LLMDevs/comments/1nl9oxo/i\_built\_rag\_systems\_for\_enterprises\_20k\_docs/](https://www.reddit.com/r/LLMDevs/comments/1nl9oxo/i_built_rag_systems_for_enterprises_20k_docs/)  
15. Leveraging RAG to search Technical Manuals \- Abeyon, accessed February 9, 2026, [https://abeyon.com/rag/](https://abeyon.com/rag/)  
16. Advanced RAG patterns on Amazon SageMaker | Artificial Intelligence \- AWS, accessed February 9, 2026, [https://aws.amazon.com/blogs/machine-learning/advanced-rag-patterns-on-amazon-sagemaker/](https://aws.amazon.com/blogs/machine-learning/advanced-rag-patterns-on-amazon-sagemaker/)  
17. RAG Document Chunking: 6 Best Practices \- Airbyte, accessed February 9, 2026, [https://airbyte.com/agentic-data/ag-document-chunking-best-practices](https://airbyte.com/agentic-data/ag-document-chunking-best-practices)  
18. Enhancing RAG performance with smart chunking strategies \- IBM Developer, accessed February 9, 2026, [https://developer.ibm.com/articles/awb-enhancing-rag-performance-chunking-strategies/](https://developer.ibm.com/articles/awb-enhancing-rag-performance-chunking-strategies/)  
19. Production RAG: The Chunking, Retrieval, and Evaluation Strategies That Actually Work, accessed February 9, 2026, [https://towardsai.net/p/machine-learning/production-rag-the-chunking-retrieval-and-evaluation-strategies-that-actually-work](https://towardsai.net/p/machine-learning/production-rag-the-chunking-retrieval-and-evaluation-strategies-that-actually-work)  
20. Chunk Twice, Retrieve Once: RAG Chunking Strategies Optimized for Different Content Types, accessed February 9, 2026, [https://infohub.delltechnologies.com/es-es/p/chunk-twice-retrieve-once-rag-chunking-strategies-optimized-for-different-content-types/](https://infohub.delltechnologies.com/es-es/p/chunk-twice-retrieve-once-rag-chunking-strategies-optimized-for-different-content-types/)  
21. Retrieval-augmented generation (RAG) failure modes and how to fix them \- Snorkel AI, accessed February 9, 2026, [https://snorkel.ai/blog/retrieval-augmented-generation-rag-failure-modes-and-how-to-fix-them/](https://snorkel.ai/blog/retrieval-augmented-generation-rag-failure-modes-and-how-to-fix-them/)  
22. Chunking and Segmentation: The Quiet Failure Point in Retrieval Quality | by Anindya Singh Obi | Dec, 2025 | Medium, accessed February 9, 2026, [https://medium.com/@anindyasinghobi/chunking-and-segmentation-the-quiet-failure-point-in-retrieval-quality-4bbb830ce7d0](https://medium.com/@anindyasinghobi/chunking-and-segmentation-the-quiet-failure-point-in-retrieval-quality-4bbb830ce7d0)  
23. Hybrid Search in PostgreSQL: The Missing Manual \- ParadeDB, accessed February 9, 2026, [https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual)  
24. How does vector search compare to hybrid search approaches? \- Milvus, accessed February 9, 2026, [https://milvus.io/ai-quick-reference/how-does-vector-search-compare-to-hybrid-search-approaches](https://milvus.io/ai-quick-reference/how-does-vector-search-compare-to-hybrid-search-approaches)  
25. Hybrid Search (BM25 \+ Vector Embeddings): The Best of Both Worlds in Information Retrieval | by Mahima Agarwal | Medium, accessed February 9, 2026, [https://medium.com/@mahima\_agarwal/hybrid-search-bm25-vector-embeddings-the-best-of-both-worlds-in-information-retrieval-0d1075fc2828](https://medium.com/@mahima_agarwal/hybrid-search-bm25-vector-embeddings-the-best-of-both-worlds-in-information-retrieval-0d1075fc2828)  
26. Hybrid Search Explained \- Weaviate, accessed February 9, 2026, [https://weaviate.io/blog/hybrid-search-explained](https://weaviate.io/blog/hybrid-search-explained)  
27. Common RAG challenges in the wild and how to solve them | by The Educative Team, accessed February 9, 2026, [https://learningdaily.dev/common-rag-challenges-in-the-wild-and-how-to-solve-them-5713bd7ad35c](https://learningdaily.dev/common-rag-challenges-in-the-wild-and-how-to-solve-them-5713bd7ad35c)  
28. RAG benchmark: Who wins in document retrieval? \- Superlinear, accessed February 9, 2026, [https://superlinear.eu/insights/articles/benchmarking-retrieval-augmented-generation-who-wins-in-document-retrieval](https://superlinear.eu/insights/articles/benchmarking-retrieval-augmented-generation-who-wins-in-document-retrieval)  
29. I built a comprehensive RAG system, and here's what I've learned \- Reddit, accessed February 9, 2026, [https://www.reddit.com/r/Rag/comments/1mmct4h/i\_built\_a\_comprehensive\_rag\_system\_and\_heres\_what/](https://www.reddit.com/r/Rag/comments/1mmct4h/i_built_a_comprehensive_rag_system_and_heres_what/)  
30. RAG Tutorial: How to Build a RAG System on a Knowledge Graph \- Neo4j, accessed February 9, 2026, [https://neo4j.com/blog/developer/rag-tutorial/](https://neo4j.com/blog/developer/rag-tutorial/)  
31. Ontologies: Blueprints for Knowledge Graph Structures \- FalkorDB, accessed February 9, 2026, [https://www.falkordb.com/blog/understanding-ontologies-knowledge-graph-schemas/](https://www.falkordb.com/blog/understanding-ontologies-knowledge-graph-schemas/)  
32. Graph RAG and LLMs: How Knowledge Graphs Can Improve AI Ideation \- Nodus Labs, accessed February 9, 2026, [https://noduslabs.com/featured/graph-rag-and-llms-how-knowledge-graphs-can-improve-ai-ideation/](https://noduslabs.com/featured/graph-rag-and-llms-how-knowledge-graphs-can-improve-ai-ideation/)  
33. Ontology, Taxonomy, and Graph standards: OWL, RDF, RDFS, SKOS | by Jay Wang, accessed February 9, 2026, [https://medium.com/@jaywang.recsys/ontology-taxonomy-and-graph-standards-owl-rdf-rdfs-skos-052db21a6027](https://medium.com/@jaywang.recsys/ontology-taxonomy-and-graph-standards-owl-rdf-rdfs-skos-052db21a6027)  
34. After seeing yet another Graph RAG demo using Neo4j with no ..., accessed February 9, 2026, [https://niklasemegard.medium.com/after-seeing-yet-another-graph-rag-demo-using-neo4j-with-no-ontology-i-decided-to-show-what-real-0d3053c2e186](https://niklasemegard.medium.com/after-seeing-yet-another-graph-rag-demo-using-neo4j-with-no-ontology-i-decided-to-show-what-real-0d3053c2e186)  
35. Releases · foundryvtt-starfinder/foundryvtt-starfinder \- GitHub, accessed February 9, 2026, [https://github.com/foundryvtt-starfinder/foundryvtt-starfinder/releases](https://github.com/foundryvtt-starfinder/foundryvtt-starfinder/releases)  
36. An Ontology-Driven Graph RAG for Legal Norms: A Hierarchical, Temporal, and Deterministic Approach \- arXiv, accessed February 9, 2026, [https://arxiv.org/html/2505.00039v4](https://arxiv.org/html/2505.00039v4)  
37. Rules for Knowledge Graphs Rules \- Dan McCreary \- Medium, accessed February 9, 2026, [https://dmccreary.medium.com/rules-for-knowledge-graphs-rules-f22587307a8f](https://dmccreary.medium.com/rules-for-knowledge-graphs-rules-f22587307a8f)  
38. Data Model | Foundry VTT Community Wiki, accessed February 9, 2026, [https://foundryvtt.wiki/en/development/api/DataModel](https://foundryvtt.wiki/en/development/api/DataModel)  
39. Introduction to System Development | Foundry Virtual Tabletop, accessed February 9, 2026, [https://foundryvtt.com/article/system-development/](https://foundryvtt.com/article/system-development/)  
40. Release 0.4.0 | Foundry Virtual Tabletop, accessed February 9, 2026, [https://foundryvtt.com/releases/4.55](https://foundryvtt.com/releases/4.55)  
41. DataModel | Foundry Virtual Tabletop \- API Documentation \- Version 13, accessed February 9, 2026, [https://foundryvtt.com/api/classes/foundry.abstract.DataModel.html](https://foundryvtt.com/api/classes/foundry.abstract.DataModel.html)  
42. foundryvtt-starfinder/changelist.md at development \- GitHub, accessed February 9, 2026, [https://github.com/foundryvtt-starfinder/foundryvtt-starfinder/blob/development/changelist.md](https://github.com/foundryvtt-starfinder/foundryvtt-starfinder/blob/development/changelist.md)  
43. How to Do Named Entity Recognition (NER) with a BERT Model \- MachineLearningMastery.com, accessed February 9, 2026, [https://machinelearningmastery.com/how-to-do-named-entity-recognition-ner-with-a-bert-model/](https://machinelearningmastery.com/how-to-do-named-entity-recognition-ner-with-a-bert-model/)  
44. Named Entity Recognition with BERT \- GeeksforGeeks, accessed February 9, 2026, [https://www.geeksforgeeks.org/data-science/named-entity-recognition-with-bert/](https://www.geeksforgeeks.org/data-science/named-entity-recognition-with-bert/)  
45. Pseudo-Knowledge Graph: Meta-Path Guided Retrieval and In-Graph Text for RAG-Equipped LLM \- arXiv, accessed February 9, 2026, [https://arxiv.org/html/2503.00309v1](https://arxiv.org/html/2503.00309v1)  
46. RAG Evaluation: Metrics, Methods, and Benchmarks That Matter \- Statsig, accessed February 9, 2026, [https://www.statsig.com/perspectives/rag-evaluation-metrics-methods-benchmarks](https://www.statsig.com/perspectives/rag-evaluation-metrics-methods-benchmarks)  
47. RAG Evaluation Metrics: Best Practices for Evaluating RAG Systems \- Patronus AI, accessed February 9, 2026, [https://www.patronus.ai/llm-testing/rag-evaluation-metrics](https://www.patronus.ai/llm-testing/rag-evaluation-metrics)  
48. Evaluating the evaluators: know your RAG metrics \- Tweag, accessed February 9, 2026, [https://tweag.io/blog/2025-02-27-rag-evaluation/](https://tweag.io/blog/2025-02-27-rag-evaluation/)  
49. Ultimate Guide to Benchmarking RAG Systems \- Artech Digital, accessed February 9, 2026, [https://www.artech-digital.com/blog/ultimate-guide-to-benchmarking-rag-systems-mfn0f](https://www.artech-digital.com/blog/ultimate-guide-to-benchmarking-rag-systems-mfn0f)  
50. 7 RAG benchmarks \- Evidently AI, accessed February 9, 2026, [https://www.evidentlyai.com/blog/rag-benchmarks](https://www.evidentlyai.com/blog/rag-benchmarks)  
51. RAG Model Benchmarking Demo \- ValidMind AI, accessed February 9, 2026, [https://docs.validmind.com/notebooks/code\_samples/nlp\_and\_llm/rag\_benchmark\_demo.html](https://docs.validmind.com/notebooks/code_samples/nlp_and_llm/rag_benchmark_demo.html)