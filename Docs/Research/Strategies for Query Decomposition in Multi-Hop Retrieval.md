Strategies for Query Decomposition in Multi‑Hop Retrieval
Overview

Query decomposition is a key technique for retrieval‑augmented generation (RAG) and multi‑hop question‑answering. Complex questions often demand evidence spread across multiple documents or sections. Query decomposition approaches break a complex query into simpler sub‑questions, retrieve evidence for each, and combine the results to produce an answer. Evidence shows that appropriately decomposing queries improves retrieval recall, downstream answer accuracy and efficiency. This survey summarises major decomposition strategies and highlights empirical results.

1. Static rule‑based and plan‑then‑execute methods

These methods decompose a query before retrieval, often using heuristics, grammar rules or supervised models to identify sub‑questions. The sub‑questions are resolved independently, and their answers are combined.

1.1 Self‑Ask

Press et al. (2022) introduced Self‑Ask, where an LLM generates an intermediate question, answers it, and then uses that answer to answer the final query. On multi‑hop datasets, Self‑Ask markedly outperformed direct prompting and even chain‑of‑thought (CoT). On the Bamboogle dataset, Davinci‑002 achieved 46.4 % accuracy with CoT but 57.6 % with self‑ask, and 60.0 % when a search engine was integrated. Self‑Ask improved performance over CoT by 11 percentage points, and adding search produced gains of up to 10 points across datasets.

1.2 Least‑to‑Most (LtM) Prompting

Zhou et al. (2023) proposed least‑to‑most prompting, where complex tasks are decomposed into a series of smaller problems whose solutions are composed. For the SCAN benchmark, LtM prompting with GPT‑3 code‑davinci‑002 achieved ≥99 % accuracy using only 14 examples, while chain‑of‑thought on the same model scored just 16 %. These results show that targeted decomposition can dramatically improve generalisation on compositional tasks.

1.3 Decompose‑and‑Query (D&Q)

D&Q uses LLMs to generate sub‑questions which are answered via a reliable QA model and combined. In HotpotQA question‑only settings, D&Q achieved an F1 of 59.6 % and matched ChatGPT’s performance in 67 % of cases. Dynamic query decomposition summaries report that D&Q improved recall from 52.3 % to 68.8 % (F1 = 59.6) on HotpotQA.

1.4 ReDI (Reason to Retrieve)

ReDI introduces a three‑stage pipeline—decomposition, interpretation of sub‑queries and fusion. On the BRIGHT dataset, ReDI’s decompose+interpret approach improved the nDCG@10 retrieval metric to 30.8 with BM25 retrieval versus 22.6 for single expansion and 20.7 for simple decomposition alone; with dense SBERT retrieval, it achieved 22.8 versus 18.4 baseline. Dynamic summarisation notes that ReDI improves nDCG@10 from 17.2 % to 38.3 % in sparse retrieval and from 17.2 % to 22.8 % in dense retrieval.

1.5 Structured query expansion & grammar‑based methods

Other plan‑then‑execute methods employ query grammars or SQL‑like parsers to generate subqueries. A query–parser–link (QPL) framework improved SQL execution accuracy from 73 % to 84 % and coverage of knowledge graphs. These approaches require hand‑crafted grammars or domain knowledge but can yield large improvements when queries have regular structure.

2. Interleaved retrieval and reasoning

Instead of fully decomposing a query in advance, these methods interleave retrieval and reasoning steps, allowing the model to decide what to retrieve next based on intermediate reasoning.

2.1 Chain‑of‑Thought with Retrieval (CoT‑R)

Interleaving retrieval with chain‑of‑thought (IRCoT) intersperses retrieval calls within a model’s reasoning process. The model reasons about the query, issues retrieval queries to fetch evidence, and continues reasoning. IRCoT improved recall by 11–21 points and increased downstream QA F1 by up to 15 points on datasets including HotpotQA, 2WikiMultiHopQA, MuSiQue and IIRC. It also reduced hallucinations by up to 50 % and performed well on smaller models like Flan‑T5.

2.2 ReAct

ReAct combines reasoning and acting by allowing the LLM to produce both internal reasoning steps and external actions such as “search” or “lookup”. On HotpotQA, a combination of ReAct with chain‑of‑thought achieved 35.1 exact match and 64.6 accuracy, outperforming standard baselines (28.7 EM, 57.1 acc) and plain CoT (29.4 EM). ReAct boosted success rates by 34 % on ALFWorld and 10 % on WebShop compared to reinforcement‑learning baselines. These results suggest that interleaving retrieval via explicit actions can yield significant gains.

2.3 Self‑Ask + Search (Self‑RAG)

An extension of self‑ask where each intermediate question triggers a search. As noted above, self‑ask+search improved accuracy by up to 10 percentage points over self‑ask alone on multiple multi‑hop datasets.

2.4 Layer‑wise retrieval (L‑RAG)

L‑RAG uses intermediate layer representations from the model to retrieve relevant passages without generating explicit sub‑questions. On 2WikiMQA, L‑RAG@8 achieved recall@8 of 0.480 compared to 0.359 for vanilla RAG; on Musique and HotpotQA the recalls at K=8 were 0.764 and 0.613 respectively. However, IRCoT and SelfAsk still achieved higher recall or accuracy on some tasks; L‑RAG’s benefit is that it avoids explicit query rewriting and may be more efficient.

2.5 FrugalRAG

FrugalRAG minimises the number of retrieval calls while maintaining performance. On HotpotQA with an 8B Llama model, ReAct with few‑shot (FS) prompting achieved recall 77.44 and support F1 83.03 using ~4.79 searches, whereas FrugalRAG improved recall to 79.62 and support F1 to 84.47 with only 2.96 searches; a version with additional exploration (FrugalRAG‑Explore) achieved recall 83.11 and F1 86.96 with 5.96 searches. This highlights that optimising retrieval strategy, not just decomposition, affects efficiency and performance.

3. Tree‑based and graph‑guided methods
3.1 Reasoning in Trees (RT‑RAG)

RT‑RAG creates a reasoning tree where each node represents a sub‑question and retrieval is performed bottom‑up. When applied to multi‑hop QA, RT‑RAG improved F1 by 7 points and exact match by 6 points compared with state‑of‑the‑art RAG methods on multi‑hop tasks.

3.2 PRISM (Selector‑Adder)**

PRISM uses an agentic loop with a question analyser and a selector‑adder mechanism that iteratively decomposes queries and adds relevant knowledge until the answer is found. On HotpotQA, PRISM achieved 66.96 F1 versus 60.7 F1 for IRCoT; on the MultiHopRAG dataset it achieved 49.16 accuracy, demonstrating state‑of‑the‑art performance. Cross‑model experiments showed that PRISM with Gemini‑2.5‑Flash‑Lite reached 70.37 F1 on HotpotQA and 44.52 F1 on MuSiQue, indicating robustness across model sizes. Ablations revealed that removing the question analyser or the selector‑adder loop reduced recall, highlighting that both decomposition and iterative refinement are crucial.

3.3 PruneRAG

PruneRAG builds a search tree but prunes unpromising branches based on confidence scores. It achieved a 5.45 % F1 improvement over strong baselines on HotpotQA and delivered 4.9× speedups by reducing the number of retrieval calls. Further analysis showed that PruneRAG attained the highest exact match and F1 scores across datasets while maintaining the fastest inference speed because it prunes low‑confidence nodes and focuses retrieval on promising subqueries. This demonstrates that dynamic control over the decomposition tree can improve both accuracy and efficiency.

3.4 Dynamic query decomposition frameworks

The EmergentMind survey summarised a range of dynamic decomposition methods. It reported that D&Q improved recall on HotpotQA from 52.3 % to 68.8 %, POQD increased QA exact match from 61.14 % to 62.22 %, and ReDI increased nDCG@10 from 17.2 % to 38.3 % in sparse retrieval. The same survey noted that QPL‑based parsers improved SQL execution accuracy from 73 % to 84 % and that adaptive node expansion (PruneRAG) yields ~4.9× speedups. These results collectively show that dynamic, context‑aware decomposition offers significant benefits.

4. Generative question‑decomposition
4.1 GenDec

GenDec is a generative question‑decomposition method that uses an LLM to produce sub‑questions. On the SQuAD dataset, adding GenDec to a baseline QA model improved F1 by 3.36 points and exact match by 2.16 points. It also improved F1 and EM by ~3–4 points on sub‑question tasks. The paper showed that GenDec outperformed other QD‑based and graph neural network methods, suggesting that generative decomposition can yield robust improvements.

5. Performance‑oriented decomposition and multi‑armed bandits

Some methods frame decomposition as an optimisation problem, where the system adaptively chooses subqueries to maximize retrieval quality.

5.1 Multi‑armed bandit policies and Orion

The EmergentMind survey notes that multi‑armed bandit policies for subquery retrieval improve precision and alpha‑nDCG in targeted retrieval contexts. Another system, Orion, uses dependency‑aware decomposition to reduce token generation cost. It achieved up to 4.33× token‑generation speed‑ups, 3.42× lower latency, and 18.75 % win‑rate improvement in streaming RAG settings. These results indicate that adaptive policies can both speed up retrieval and improve outcomes.

5.2 Performance‑Oriented Query Decomposer (POQD)

POQD optimises query decomposition by ranking candidate sub‑queries based on potential retrieval benefit. According to dynamic decomposition summaries, POQD improved QA exact match from 61.14 % to 62.22 % compared with the ColBERT baseline. Although the absolute improvement is modest, POQD demonstrates that optimising the decomposition process itself can yield measurable gains.

6. Summary and recommendations
6.1 Evidence of effectiveness

Static decomposition methods (Self‑Ask, D&Q, ReDI) show clear gains in recall, nDCG and F1 across multiple datasets. Self‑Ask improved accuracy by ~11 percentage points over chain‑of‑thought and further by up to 10 points when combined with search. ReDI and D&Q demonstrate that simple but well‑designed decompositions can improve retrieval quality by 5–10 points.

Interleaved retrieval & reasoning (IRCoT, ReAct, Self‑Ask+Search) often yield the largest improvements in QA accuracy. IRCoT improves recall by 11–21 points and F1 by up to 15 points. ReAct combined with chain‑of‑thought achieved 35.1 EM and 64.6 accuracy on HotpotQA, outperforming baselines.

Tree‑based methods (RT‑RAG, PRISM, PruneRAG) offer state‑of‑the‑art results. PRISM achieved F1 66.96 on HotpotQA, beating IRCoT by ~6 points. PruneRAG improved F1 by 5.45 % with a 4.9× speedup, illustrating that dynamic pruning reduces cost while raising accuracy.

Generative decomposers like GenDec provide consistent F1/EM gains (~3–4 points) on QA tasks. They are promising when combined with strong base models.

Performance‑oriented policies (multi‑armed bandits, POQD, Orion) optimise the decomposition process for cost and quality. These methods yield efficiency gains (4.33× speed‑ups and 18.75 % win‑rate improvement) while maintaining or slightly improving accuracy.

6.2 When decomposition helps and when it does not

A study on machine reading found that decompositions provide only minor gains in exact match and sometimes hurt performance when large training data is available. This suggests that decomposition is most beneficial in low‑data or complex multi‑hop settings where retrieval remains a bottleneck. In high‑data regimes or tasks with simple reasoning, direct retrieval may suffice.

6.3 Practical recommendations

Start with simple decomposition: For many RAG systems, even basic self‑ask or D&Q‑style decomposition can improve recall and accuracy without heavy engineering.

Integrate retrieval and reasoning: Methods like IRCoT and ReAct show that interleaving search with reasoning yields strong gains; they avoid over‑decomposing by letting the model decide when to search.

Use tree‑based controllers for harder tasks: RT‑RAG, PRISM and PruneRAG combine decomposition with dynamic control to manage search depth and avoid explosions in sub‑questions. They deliver state‑of‑the‑art performance but require more complex orchestration.

Optimise for efficiency: Frameworks like FrugalRAG and Orion demonstrate that query decomposition can be tuned for efficiency without sacrificing much accuracy; pruning low‑confidence branches and adaptive policies are key techniques.

Evaluate decomposition modules separately: When building a retrieval system, measure the benefit of decomposition alone, retrieval alone, and combined approaches. Many studies show synergy when combined with reranking or re‑prompting (e.g., question decomposition + reranking improved Hits@10 by 16.5 % and MRR@10 by 8.4 % on MultiHop‑RAG).

Conclusion

Research on query decomposition for retrieval‑augmented generation demonstrates that breaking down complex queries into simpler sub‑questions can meaningfully improve retrieval recall, answer accuracy and efficiency. Successful strategies include static decomposition (Self‑Ask, ReDI), interleaving retrieval and reasoning (IRCoT, ReAct), tree‑based search (PRISM, PruneRAG) and generative decomposers (GenDec). Dynamic and performance‑oriented approaches further optimise the process, reducing cost while maintaining strong results. However, decomposition is not universally beneficial; its advantages are largest on multi‑hop or low‑data tasks and may diminish in high‑data regimes. Careful evaluation and integration of decomposition techniques remain essential for building effective RAG systems.