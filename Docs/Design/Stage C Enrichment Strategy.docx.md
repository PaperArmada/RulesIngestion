# Benchmark design for PF2e multihop retrieval

## Context

Pathfinder 2e (PF2e) rules contain highly interconnected classes, feats, and tables. Initial experiments with a **hybrid baseline** retriever (dense model all‑mpnet‑base‑v2 plus cross‑concept (CC) fusion) on a **pilot set of 10 multihop questions** showed that the retriever consistently returned at least one gold evidence unit (gold\_in\_candidates = 1.0), but it rarely assembled the full evidence chain. For example, the mean rank of the last required anchor was ≈ 9, and only **one** query had all required gold facts within the top‑10 candidates. Large multi‑anchor queries with 5–8 required evidence units were particularly problematic, because **Hit@10** or **Recall@10** provided a binary success/failure signal that failed to reflect partial improvements (e.g., retrieving 7 of 8 anchors still scored zero under ReqFSH@10).

To make progress, we want a benchmark that both stresses end‑to‑end multihop retrieval (reassembling the entire evidence set) and provides **fine‑grained diagnostic feedback** when the system improves some hops but not others. Splitting large questions into **micro‑bundles** (smaller query–answer units) can sharpen the evaluation signal. Meanwhile, we want to learn from existing multi‑hop benchmarks used in the wider QA community and adapt their design principles to PF2e.

## Why micro‑bundles?

A “micro‑bundle” is a small benchmark unit that targets one particular evidence‑assembly obligation. Suppose a query implicitly requires eight distinct anchor facts to answer. Under the current metric ReqFSH@10 (required full‑set hit@10), the query scores **1** only if all eight anchors are found within the top‑10; otherwise it scores **0**, even if the system returns seven of them. This makes the metric **coarse** and slows down iteration:

* **Low sensitivity:** going from 1/8 to 7/8 anchors within the top‑10 is a huge real improvement but still scores 0\.

* **Poor diagnostics:** we cannot tell which hop failed—was it candidate discovery (the missing anchor wasn’t retrieved at all) or ranking depth (it’s in the pool but beyond the top‑10)?

By splitting the question into micro‑bundles, each requiring only one or two anchors, we make the metric sharper. Each micro‑bundle asks, for example: “Which feats qualify the character for this level requirement?” or “Which rules govern stacking exceptions for a Solarian and Lashunta lineage?” The micro‑bundled metric flips from 0 to 1 once the necessary small evidence set appears in the top‑10, giving clear feedback about specific retrieval deficiencies.

The full macro question is still important: it tests whether the system can assemble **all** evidence under a realistic top‑k cap. However, pairing it with micro‑bundled diagnostics allows us to see partial progress instead of waiting for perfect assembly.

## Proposed dual‑surface benchmark

The PF2e multihop benchmark should therefore include two distinct evaluation surfaces:

1. **Multihop end‑to‑end surface** – the original user‑shaped questions (e.g., “What feats and rules allow a Lashunta Solarian to take the Early Ascetic Dedication at level 4 and how do they interact with ancestry‑feat stacking?”). Metrics should include:

2. **MRR**, **Hit@k**, **Recall@k**, and **ReqFSH@10** (required full‑set hit@10).

3. **Last required rank** (mean rank of the last gold evidence unit in the top‑10).

4. Diagnostic counts: number of gold units found, candidates added per operator, etc.

This surface remains our “production‑readiness” benchmark: it reflects real user tasks and measures whether the system can assemble the entire evidence chain within a tight retrieval budget.

1. **Micro‑bundled diagnostic surface** – each complex question is decomposed into several **micro‑questions**, each mapped to a small set of required anchors (often one or two). Micro‑bundles can target:

2. **Feat discovery** – identify all feats that satisfy a given level and class constraint.

3. **Baseline rule interactions** – identify which base rules interact with a particular feat or class ability.

4. **Exception/stacking rules** – identify exceptions that override a base rule in the context of a specific combination.

For each micro‑bundle, we compute ReqFSH@10, Recall@10, and Hit@k on the much smaller gold set. Because the required set is small, the metric flips from 0 to 1 when that small evidence group appears in the top‑10. This gives a more **interpretable signal** about which hop is failing and helps iterate on retrieval strategies.

### Evaluation structure

* **Working set vs. clean subset:** As described in the updated Retrieval Lab documentation, experiments should specify whether they evaluate on the **full working set** (all benchmark queries) or a **clean subset** (ratified, core queries). For our pilot, the diagnostic micro‑bundles can remain in the working set until they are ratified.

* **Comparison surfaces:** Dense‑only baseline, hybrid baseline (dense \+ cross‑concept fusion), and future Stage C/Stage D retrieval systems should all be evaluated on both surfaces. Improvements on the micro‑bundles will indicate progress toward eventual end‑to‑end success.

* **Answer evaluation:** When answer generation is introduced, the benchmark should use Retrieval Lab’s **answer‑evaluation** stage, which scores generated answers for correctness, completeness, and citation fidelity. However, even without generation, micro‑bundles help evaluate retrieval alone.

## Lessons from existing multi‑hop benchmarks

Multi‑hop question‑answering and retrieval has been studied in various domains. Existing benchmarks provide design patterns we can adapt.

### HotpotQA and BeerQA

HotpotQA was one of the earliest large‑scale multi‑hop QA datasets. It features **natural, multi‑hop questions** with “strong supervision for supporting facts”[\[1\]](https://hotpotqa.github.io/#:~:text=). Models must retrieve two disjoint paragraphs and provide supporting sentences. The dataset emphasises **supporting‑fact supervision** and uses metrics like exact match (EM), F1 on answers, and EM/F1 on supporting facts. BeerQA builds on HotpotQA and SQuAD and introduces open‑domain questions that may require **varying hops**. BeerQA emphasises questions that need information from **multiple Wikipedia documents** and uses EM and F1 metrics across different subsets[\[2\]](https://beerqa.github.io/#:~:text=A%20Dataset%20for%20Open,Question%20Answering). HotpotQA’s strong supporting‑fact supervision and BeerQA’s multi‑document structure demonstrate that benchmarks should both measure answer correctness and provide **supervision for evidence retrieval**.

### HybridQA and MuSiQue

HybridQA requires reasoning over **heterogeneous information**: a Wikipedia table and multiple linked text passages. The dataset contains \~13k tables, 293k hyperlinked passages and \~70k natural questions[\[3\]](https://hybridqa.github.io/#:~:text=A%20large,tabular%20and%20unstructured%20textual%20forms). This heterogeneity forced the development of retrieval models that handle both tabular and textual information. PF2e retrieval faces a similar challenge: rules are spread across tables (feat lists, class progression tables) and textual descriptions. HybridQA’s design suggests the need for retrieval strategies that operate across structured and unstructured data.

MuSiQue introduced a **bottom‑up construction** for multi‑hop questions by composing single‑hop QA pairs and enforcing a **connected reasoning graph**. The resulting dataset contains 25k questions requiring **2–4 hops** and includes **unanswerable contrast questions**[\[4\]](https://arxiv.org/abs/2108.00573#:~:text=,that%20perform%20genuine%20multihop%20reasoning). MuSiQue’s design emphasises strict control to prevent reasoning shortcuts and provides fine‑grained sub‑question annotation. This bottom‑up approach inspired the idea of micro‑bundles: by breaking questions into small, connected hops, evaluation can monitor each step and prevent the model from skipping necessary evidence.

### FanOutQA

FanOutQA addresses **fan‑out questions**, where the answer requires collecting information about multiple entities from many documents. The dataset contains **1,034 questions** with **7,305 human‑written decompositions** and an average of **seven reasoning hops**[\[5\]](https://aclanthology.org/2024.acl-short.2.pdf#:~:text=ity%20dataset%20of%201%2C034%20information,provided%20setting%20provides%2018). FanOutQA formulates three settings: **closed book**, **open book**, and **evidence‑provided**, showing that even state‑of‑the‑art LLMs struggle when the answer requires aggregating information across many documents[\[6\]](https://aclanthology.org/2024.acl-short.2.pdf#:~:text=over%20the%20dataset.%20The%20closed,provided%20setting%20provides%2018). This is similar to PF2e queries that require fetching lists of feats or multiple interacting rules. FanOutQA’s multi‑hop evaluation and its use of **human‑written decompositions** demonstrate that explicit decomposition can make evaluation clearer.

### MultiHop‑RAG

MultiHop‑RAG introduces a dataset for evaluating **retrieval‑augmented generation (RAG)** systems on multi‑hop queries. It provides a knowledge base, a collection of multi‑hop queries, their answers and supporting evidence. Experiments show that current RAG methods perform poorly on multi‑hop retrieval tasks[\[7\]](https://arxiv.org/abs/2401.15391#:~:text=%3E%20Abstract%3ARetrieval,for%20the%20community%20in%20developing). The authors highlight that no previous RAG benchmark focused on multi‑hop retrieval[\[7\]](https://arxiv.org/abs/2401.15391#:~:text=%3E%20Abstract%3ARetrieval,for%20the%20community%20in%20developing), emphasising the need to evaluate retrieval ability separately from answer generation—exactly what our micro‑bundles aim to do.

### MINTQA and MEQA

MINTQA (Multi‑hop QA on **New and Tail Knowledge**) evaluates LLMs’ ability to handle **new or long‑tail knowledge**. It comprises **10,479 question‑answer pairs** for new knowledge and **17,887 pairs** for tail knowledge[\[8\]](https://arxiv.org/abs/2412.17032#:~:text=,MINTQA%20benchmark%20is%20available%20at). Each question is accompanied by **sub‑questions and answers**, and the benchmark evaluates four dimensions: question handling strategy, sub‑question generation, retrieval‑augmented generation, and iterative retrieval[\[8\]](https://arxiv.org/abs/2412.17032#:~:text=,MINTQA%20benchmark%20is%20available%20at). MINTQA shows that LLMs struggle with complex multi‑hop queries involving obscure knowledge and that explicit sub‑question annotation helps evaluation. MEQA (Multi‑hop Event‑centric QA) focuses on event‑centric questions, emphasising event‑event and entity‑event relations and providing reasoning chains (explanations) for each question[\[9\]](https://proceedings.neurips.cc/paper_files/paper/2024/file/e560a0b22e4432003d0dba63ff8dc457-Paper-Datasets_and_Benchmarks_Track.pdf#:~:text=Answering%20%28MEQA%29%20benchmark1,We%20also%20introduce). These datasets show that **novelty control** and **explicit reasoning chains** help avoid memorisation and support fine‑grained evaluation.

### Lessons for PF2e

From these benchmarks we learn several design principles:

1. **Strong evidence supervision:** Provide gold supporting facts or units for each question, so the retriever can be evaluated separately from the answer generator (HotpotQA, HybridQA).

2. **Heterogeneous retrieval:** Include both structured (tables) and unstructured (text) information as first‑class citizens (HybridQA). PF2e retrieval must handle tables (feat lists) and text (rules and descriptions).

3. **Sub‑question decomposition:** Break down multi‑hop questions into explicit sub‑questions or micro‑bundles to evaluate each reasoning step separately (MuSiQue, MINTQA, FanOutQA). This improves diagnostic power and prevents shortcuts.

4. **Novelty and difficulty control:** Consider stratifying queries by difficulty (number of hops, semantic similarity) and novelty (popular vs. long‑tail knowledge) (MINTQA, MuSiQue). For PF2e, difficulty could correlate with the number of anchors and the complexity of rule interactions.

5. **RAG‑specific evaluation:** Evaluate retrieval and generation separately for multi‑hop tasks (MultiHop‑RAG). This aligns with our plan to benchmark retrieval alone with micro‑bundles before adding answer generation.

## Are there benchmarks for TTRPG/rules retrieval?

There is no widely known multi‑hop benchmark specifically for tabletop role‑playing game (TTRPG) rules. Most multi‑hop QA datasets are built on open‑domain corpora (Wikipedia, news, knowledge graphs) or hybrid tabular/text data. PF2e has idiosyncratic structure (feat tables, progression charts, cross‑book references) and restricted content (licensed rulebooks). Therefore we cannot directly reuse existing datasets, but we can **model our benchmark design** on the principles above:

* Use the PF2e Player Core book and related rule documents as the corpus.

* Construct questions that require combining multiple rule fragments (multihop), including table entries and textual descriptions.

* Provide gold evidence units for each question (the list of rule paragraphs and table rows needed to answer).

* Split large questions into micro‑bundles with explicit sub‑questions or evidence obligations for diagnostic evaluation.

* Use metrics analogous to HotpotQA’s evidence F1 and MuSiQue’s sub‑question evaluation, adapted to our retrieval evaluation (MRR, Hit@k, ReqFSH@k, coverage at top‑k).

## Conclusion and next steps

Baseline experiments show that PF2e multihop retrieval is inadequate at assembling full evidence chains. Splitting queries into micro‑bundles will sharpen evaluation, enabling us to identify which hops are failing and whether improvements (e.g., query decomposition, structural expansion, Stage C enrichment) actually fix them. Existing benchmarks in the QA community confirm that **explicit decomposition** and **strong evidence supervision** are key to multi‑hop evaluation, and they also illustrate how to handle heterogeneous sources and long‑tail knowledge.

The proposed dual‑surface benchmark—end‑to‑end multihop and micro‑bundled diagnostics—incorporates these insights while remaining faithful to the PF2e architecture. Future work includes formalizing the micro‑bundle schema, selecting representative PF2e questions and sub‑questions, and integrating answer evaluation into Retrieval Lab once retrieval quality improves.

---

[\[1\]](https://hotpotqa.github.io/#:~:text=) HotpotQA Homepage

[https://hotpotqa.github.io/](https://hotpotqa.github.io/)

[\[2\]](https://beerqa.github.io/#:~:text=A%20Dataset%20for%20Open,Question%20Answering) BeerQA Homepage

[https://beerqa.github.io/](https://beerqa.github.io/)

[\[3\]](https://hybridqa.github.io/#:~:text=A%20large,tabular%20and%20unstructured%20textual%20forms) HybridQA

[https://hybridqa.github.io/](https://hybridqa.github.io/)

[\[4\]](https://arxiv.org/abs/2108.00573#:~:text=,that%20perform%20genuine%20multihop%20reasoning) \[2108.00573\] MuSiQue: Multihop Questions via Single-hop Question Composition

[https://arxiv.org/abs/2108.00573](https://arxiv.org/abs/2108.00573)

[\[5\]](https://aclanthology.org/2024.acl-short.2.pdf#:~:text=ity%20dataset%20of%201%2C034%20information,provided%20setting%20provides%2018) [\[6\]](https://aclanthology.org/2024.acl-short.2.pdf#:~:text=over%20the%20dataset.%20The%20closed,provided%20setting%20provides%2018) 2024.acl-short.2.pdf

[https://aclanthology.org/2024.acl-short.2.pdf](https://aclanthology.org/2024.acl-short.2.pdf)

[\[7\]](https://arxiv.org/abs/2401.15391#:~:text=%3E%20Abstract%3ARetrieval,for%20the%20community%20in%20developing) \[2401.15391\] MultiHop-RAG: Benchmarking Retrieval-Augmented Generation for Multi-Hop Queries

[https://arxiv.org/abs/2401.15391](https://arxiv.org/abs/2401.15391)

[\[8\]](https://arxiv.org/abs/2412.17032#:~:text=,MINTQA%20benchmark%20is%20available%20at) \[2412.17032\] MINTQA: A Multi-Hop Question Answering Benchmark for Evaluating LLMs on New and Tail Knowledge

[https://arxiv.org/abs/2412.17032](https://arxiv.org/abs/2412.17032)

[\[9\]](https://proceedings.neurips.cc/paper_files/paper/2024/file/e560a0b22e4432003d0dba63ff8dc457-Paper-Datasets_and_Benchmarks_Track.pdf#:~:text=Answering%20%28MEQA%29%20benchmark1,We%20also%20introduce) e560a0b22e4432003d0dba63ff8dc457-Paper-Datasets\_and\_Benchmarks\_Track.pdf

[https://proceedings.neurips.cc/paper\_files/paper/2024/file/e560a0b22e4432003d0dba63ff8dc457-Paper-Datasets\_and\_Benchmarks\_Track.pdf](https://proceedings.neurips.cc/paper_files/paper/2024/file/e560a0b22e4432003d0dba63ff8dc457-Paper-Datasets_and_Benchmarks_Track.pdf)