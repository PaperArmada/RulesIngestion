# Optimal Retrieval Configuration for Embedding Models

## Purpose and context

This document summarizes the recommended **inference configuration** for several popular open‑weights embedding models used in the Retrieval Lab experiments (Starfinder 2e and Swords & Wizardry). Each model has different architectural assumptions about pooling, normalization, instruction prefixes and maximum sequence lengths. Following the model authors’ guidelines is important for achieving the best retrieval quality. Where official guidance exists, citations to official documentation or model cards are provided.

## Sentence‑Transformers all‑mpnet‑base‑v2

* **Pooling and normalization.** all‑mpnet‑base‑v2 is a Sentence Transformers model that uses **mean pooling** over the final hidden states and then **L2‑normalizes** the resulting vector. The Hugging Face model card gives a reference implementation using mean\_pooling followed by F.normalize[\[1\]](https://huggingface.co/sentence-transformers/all-mpnet-base-v2#:~:text=%23Mean%20Pooling%20,9). When using Transformers directly, you must implement the pooling yourself; the Sentence Transformers wrapper does this automatically.

* **Input length.** Inputs longer than 256 WordPiece tokens are truncated by default[\[2\]](https://huggingface.co/sentence-transformers/all-mpnet-base-v2#:~:text=specification%20huggingface). For consistency, keep query and document chunks within this limit or adjust the tokenizer’s max\_length as needed.

* **Embedding dimension and storage.** The model produces 768‑d vectors and is relatively small (110 MB) and fast. Use float16 to reduce GPU memory if desired.

* **Recommended recipe.**

* \# sentence-transformers wrapper handles pooling/normalization  
  from sentence\_transformers import SentenceTransformer  
  model \= SentenceTransformer('sentence-transformers/all-mpnet-base-v2')  
  embeddings \= model.encode(texts, batch\_size=BATCH\_SIZE, show\_progress\_bar=False)  
  \# embeddings are 768‑d L2‑normalized vectors

* or, using pure Transformers:

* from transformers import AutoTokenizer, AutoModel  
  import torch.nn.functional as F  
  tokenizer \= AutoTokenizer.from\_pretrained('sentence-transformers/all-mpnet-base-v2')  
  model \= AutoModel.from\_pretrained('sentence-transformers/all-mpnet-base-v2')  
  tokens \= tokenizer(texts, padding=True, truncation=True, return\_tensors='pt')  
  with torch.no\_grad():  
      outputs \= model(\*\*tokens)  
  \# mean‑pooling over token embeddings and L2 norm  
  def mean\_pooling(last\_hidden\_state, attention\_mask):  
      input\_mask\_expanded \= attention\_mask.unsqueeze(-1).expand(last\_hidden\_state.size()).float()  
      return (last\_hidden\_state \* input\_mask\_expanded).sum(dim=1) / input\_mask\_expanded.sum(dim=1).clamp(min=1e-9)  
  embeddings \= mean\_pooling(outputs\[0\], tokens\['attention\_mask'\])  
  embeddings \= F.normalize(embeddings, p=2, dim=1)

## Nomic‑AI nomic‑embed‑text‑v2‑moe

* **Instruction prefixes.** This model requires **task instruction prefixes**: prefix queries with "search\_query: " and documents with "search\_document: "[\[3\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=,which%20task%20is%20being%20performed)[\[4\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=Best%20Practices). Without the prefix the model may treat text as generic and produce lower quality embeddings.

* **Pooling and normalization.** The recommended pooling strategy is **mean pooling** followed by **L2 normalization**[\[5\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=def%20mean_pooling,9). The model card shows an example using mean\_pooling and F.normalize in PyTorch.

* **Matryoshka dimension / truncation.** The model supports **flexible dimensions** from 768 down to 256 using Matryoshka Representation Learning. For storage or latency sensitive applications you can truncate the embeddings (e.g., keep only the first 256 dimensions) and then re‑normalize[\[6\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=For%20truncation%2C%20you%20can%20trucate,before%20applying%20normalization)[\[7\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=Best%20Practices). The default dimension is 768.

* **Maximum sequence length.** Up to **512 tokens**[\[8\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=,if%20storage%2Fcompute%20is%20a%20concern). Longer inputs should be chunked and indexed separately.

* **Other requirements.** You must load the model with trust\_remote\_code=True and install megablocks for fast GPU inference (see model card). The mixture‑of‑experts architecture uses more VRAM than typical dense models.

* **Recommended recipe.**

* from sentence\_transformers import SentenceTransformer  
  model \= SentenceTransformer('nomic-ai/nomic-embed-text-v2-moe', trust\_remote\_code=True)  
  \# specify prompt\_name so the wrapper automatically prefixes  
  embeddings\_query \= model.encode(queries, prompt\_name="query")  
  embeddings\_doc \= model.encode(documents, prompt\_name="passage")  
  \# embeddings are 768‑d L2‑normalized vectors; truncate if needed  
  embeddings\_256 \= F.normalize(embeddings\[:, :256\], p=2, dim=1)

## BAAI bge‑m3

* **Pooling and normalization.** For dense retrieval, BGE M3 uses the **hidden state of the first token (\[CLS\])** as the sentence embedding and applies **L2 normalization**[\[9\]](https://bge-model.com/tutorial/1_Embedding/1.2.4.html#:~:text=Using%20BGE%20M3%20for%20dense,5%20models). The BGE documentation warns that using mean pooling causes a significant performance drop[\[10\]](https://bge-model.com/tutorial/1_Embedding/1.2.3.html#:~:text=Different%20from%20more%20commonly%20used,as%20the%20sentence%20embedding). Obtain the embedding using e\_q \= norm(H\_q\[0\]) for queries and passages.

* **Hybrid retrieval.** The model supports **dense**, **sparse** and **multi‑vector** embeddings and can produce all three in one pass. The authors recommend a **hybrid retrieval \+ re‑ranking pipeline**: combine dense and sparse retrieval and then re‑rank candidates with a cross‑encoder[\[11\]](https://huggingface.co/BAAI/bge-m3#:~:text=Some%20suggestions%20for%20retrieval%20pipeline,in%20RAG). Hybrid retrieval can improve accuracy while keeping latency manageable.

* **Sequence length.** Up to **8192 tokens** are supported[\[12\]](https://bge-model.com/tutorial/1_Embedding/1.2.4.html#:~:text=Using%20BGE%20M3%20for%20dense,5%20models). For long documents you may choose a smaller max\_length to speed up encoding.

* **No instruction prefix.** Unlike earlier BGE models, BGE M3 does **not require instruction strings** for queries[\[13\]](https://huggingface.co/BAAI/bge-m3#:~:text=For%20embedding%20retrieval%2C%20you%20can,adding%20instructions%20to%20the%20queries).

* **Other modes.** Setting return\_sparse=True yields a lexical weight vector (similar to BM25) for each term[\[14\]](https://bge-model.com/tutorial/1_Embedding/1.2.4.html#:~:text=2.2%20Sparse%20Retrieval), and return\_colbert\_vecs=True produces multiple per‑token embeddings for late interaction[\[15\]](https://bge-model.com/tutorial/1_Embedding/1.2.4.html#:~:text=2.3%20Multi). Hybrid scoring can combine these signals with weights (s\_rank \= w₁·s\_dense \+ w₂·s\_lex \+ w₃·s\_mul)[\[16\]](https://bge-model.com/tutorial/1_Embedding/1.2.4.html#:~:text=2.4%20Hybrid%20Ranking).

* **Recommended recipe (dense‑only).**

* from FlagEmbedding import BGEM3FlagModel  
  model \= BGEM3FlagModel('BAAI/bge-m3', use\_fp16=True)  
  embeddings\_q \= model.encode(queries, max\_length=MAX\_LEN)\['dense\_vecs'\]  \# first token \+ normalized  
  embeddings\_p \= model.encode(passages, max\_length=MAX\_LEN)\['dense\_vecs'\]  
  \# similarity \= embeddings\_q @ embeddings\_p.T

* For hybrid retrieval you may also retrieve lexical\_weights and colbert\_vecs and combine scores accordingly.

## Perplexity pplx‑embed‑v1‑0.6B (standard)

* **Pooling and normalization.** Perplexity’s standard embedding models use **mean pooling** and emit **unnormalized int8 embeddings**. The model card lists the pooling method as **Mean**[\[17\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=Model%20Dimensions%20Context%20MRL%20Quantization,32K%20Yes%20INT8%2FBINARY%20No%20Mean) and states that the embeddings are unnormalized and quantized to int8[\[18\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=%3E%20%60pplx,compare%20them%20via%20cosine%20similarity). When using Text Embeddings Inference (TEI), you must compare vectors using **cosine similarity** with these unnormalized int8 values[\[19\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=%3E%20Currently%2C%20only%20int8,similarity%20with%20unnormalized%20int8%20embeddings). Do *not* apply L2 normalization; normalizing int8 vectors changes the quantization scale.

* **No instruction prefix.** The models embed text directly without requiring an instruction string[\[20\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=All%20models%20are%20built%20on,trained%20Qwen3%20at%20Perplexity%20AI).

* **Sequence length.** Up to **32 k tokens**[\[21\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=Model%20Dimensions%20Context%20MRL%20Quantization,32K%20Yes%20INT8%2FBINARY%20No%20Mean), so documents and long sections can be embedded without sliding windows.

* **Matryoshka dimension.** Perplexity models support Matryoshka dimension; you can specify a smaller output dimension (128–1024) when using TEI’s dimensions parameter to reduce storage; however, note that smaller dimensions may reduce quality.

* **Recommended recipe.**

* from sentence\_transformers import SentenceTransformer  
  model \= SentenceTransformer('perplexity-ai/pplx-embed-v1-0.6B', trust\_remote\_code=True)  
  \# encode returns int8 embeddings; do not normalize  
  embeddings \= model.encode(texts)  \# shape (n, 1024\)  
  \# compute cosine similarity between unnormalized vectors

* When using TEI or ONNX, ensure you request int8 outputs and compute cosine similarity on the raw int8 vectors.

## Perplexity pplx‑embed‑context‑v1‑0.6B (contextual)

* **Purpose.** Contextual models produce embeddings for **chunks within a document** while incorporating long‑range document context. Use them to encode document chunks and pair them with standard embeddings for queries.

* **Pooling and normalization.** All contextual models use **mean pooling** and do not require instruction prefixes[\[22\]](https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings#:~:text=All%20models%20use%20mean%20pooling,and%20require%20no%20instruction%20prefix). The API returns unnormalized int8 embeddings per chunk, similar to the standard model.

* **Input format and ordering.** The Perplexity docs require that you pass a list of chunks per document as a nested array and preserve the **original order** of chunks[\[23\]](https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings#:~:text=Basic%20Usage). The sequential context is used to compute document‑aware embeddings; mis‑ordering chunks will degrade quality.

* **Matryoshka dimension.** You can specify an output dimension between 128 and 1 024 for the 0.6B model (or 128–2 560 for the 4B model) via the dimensions parameter[\[24\]](https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings#:~:text=Parameter%20Type%20Required%20Default%20Description,2560%20for%204b).

* **Recommended usage.**

* from transformers import AutoModel  
  model\_ctx \= AutoModel.from\_pretrained('perplexity-ai/pplx-embed-context-v1-0.6B', trust\_remote\_code=True)  
  \# doc\_chunks: list of lists, where each inner list contains the chunks of one document in order  
  embeddings \= model\_ctx.encode(doc\_chunks)  \# returns list of numpy arrays, one per document  
  \# each numpy array has shape (num\_chunks, 1024\) with int8 values  
  \# compute cosine similarity between each chunk embedding and the query embedding (from pplx‑embed‑v1)

* For API use, call the contextualized embeddings endpoint with nested arrays as shown in the documentation[\[23\]](https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings#:~:text=Basic%20Usage).

## General retrieval best practices

* **Use the model’s intended pooling method.** Some models (BGE M3) use \[CLS\] pooling, while others (MPNet, Nomic, Perplexity) use mean pooling. Using the wrong pooling method can significantly degrade performance[\[10\]](https://bge-model.com/tutorial/1_Embedding/1.2.3.html#:~:text=Different%20from%20more%20commonly%20used,as%20the%20sentence%20embedding).

* **Normalize embeddings when appropriate.** Models trained under contrastive objectives (MPNet, Nomic, BGE M3) expect L2‑normalized embeddings; apply F.normalize after pooling. Do **not** normalize Perplexity’s int8 embeddings; instead compute cosine similarity directly on the raw int8 values[\[18\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=%3E%20%60pplx,compare%20them%20via%20cosine%20similarity).

* **Follow instruction prefix rules.** Models like nomic‑embed‑text‑v2‑moe require task prefixes (search\_query: for queries and search\_document: for documents)[\[3\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=,which%20task%20is%20being%20performed). BGE M3 and Perplexity models do not require prefixes.[\[20\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=All%20models%20are%20built%20on,trained%20Qwen3%20at%20Perplexity%20AI)

* **Sequence length and chunking.** Respect each model’s maximum sequence length (256 for MiniLM, 512 for Nomic, 8 192 for BGE M3, 32 k for Perplexity). For longer inputs, divide documents into coherent chunks (e.g., paragraphs or sections) and embed each chunk separately.

* **Hybrid retrieval and re‑ranking.** For models that support multiple retrieval signals (BGE M3’s dense and sparse outputs), hybrid retrieval combining BM25 or lexical weights with dense embeddings and re‑ranking with a cross‑encoder can yield better accuracy[\[11\]](https://huggingface.co/BAAI/bge-m3#:~:text=Some%20suggestions%20for%20retrieval%20pipeline,in%20RAG).

## Summary table

| Model | Pooling & normalization | Instruction prefix | Max input length | Notes |
| :---- | :---- | :---- | :---- | :---- |
| **all‑mpnet‑base‑v2** | Mean pooling \+ L2 normalization[\[1\]](https://huggingface.co/sentence-transformers/all-mpnet-base-v2#:~:text=%23Mean%20Pooling%20,9) | None | 256 tokens[\[2\]](https://huggingface.co/sentence-transformers/all-mpnet-base-v2#:~:text=specification%20huggingface) | Fast baseline; 768‑d vector |
| **nomic‑embed‑text‑v2‑moe** | Mean pooling \+ L2 normalization[\[5\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=def%20mean_pooling,9) | search\_query: / search\_document:[\[3\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=,which%20task%20is%20being%20performed) | 512 tokens[\[8\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=,if%20storage%2Fcompute%20is%20a%20concern) | Use Matryoshka truncation for 256‑d; mixture‑of‑experts; requires trust\_remote\_code=True |
| **bge‑m3** | CLS token \+ L2 normalization[\[9\]](https://bge-model.com/tutorial/1_Embedding/1.2.4.html#:~:text=Using%20BGE%20M3%20for%20dense,5%20models)[\[10\]](https://bge-model.com/tutorial/1_Embedding/1.2.3.html#:~:text=Different%20from%20more%20commonly%20used,as%20the%20sentence%20embedding) | None[\[13\]](https://huggingface.co/BAAI/bge-m3#:~:text=For%20embedding%20retrieval%2C%20you%20can,adding%20instructions%20to%20the%20queries) | 8 192 tokens[\[12\]](https://bge-model.com/tutorial/1_Embedding/1.2.4.html#:~:text=Using%20BGE%20M3%20for%20dense,5%20models) | Supports dense, sparse and multi‑vector outputs; hybrid retrieval recommended[\[11\]](https://huggingface.co/BAAI/bge-m3#:~:text=Some%20suggestions%20for%20retrieval%20pipeline,in%20RAG) |
| **pplx‑embed‑v1‑0.6B** | Mean pooling, unnormalized int8 embeddings[\[18\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=%3E%20%60pplx,compare%20them%20via%20cosine%20similarity)[\[17\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=Model%20Dimensions%20Context%20MRL%20Quantization,32K%20Yes%20INT8%2FBINARY%20No%20Mean) | None[\[20\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=All%20models%20are%20built%20on,trained%20Qwen3%20at%20Perplexity%20AI) | 32 k tokens[\[21\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=Model%20Dimensions%20Context%20MRL%20Quantization,32K%20Yes%20INT8%2FBINARY%20No%20Mean) | Compare vectors via cosine similarity on raw int8 values[\[19\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=%3E%20Currently%2C%20only%20int8,similarity%20with%20unnormalized%20int8%20embeddings); can specify Matryoshka dimension |
| **pplx‑embed‑context‑v1‑0.6B** | Mean pooling per chunk; unnormalized int8 embeddings[\[22\]](https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings#:~:text=All%20models%20use%20mean%20pooling,and%20require%20no%20instruction%20prefix) | None[\[22\]](https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings#:~:text=All%20models%20use%20mean%20pooling,and%20require%20no%20instruction%20prefix) | 32 k tokens (context window) | Input as ordered list of chunks[\[23\]](https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings#:~:text=Basic%20Usage); output per‑chunk embeddings; specify dimension (128–1024)[\[24\]](https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings#:~:text=Parameter%20Type%20Required%20Default%20Description,2560%20for%204b) |

---

[\[1\]](https://huggingface.co/sentence-transformers/all-mpnet-base-v2#:~:text=%23Mean%20Pooling%20,9) [\[2\]](https://huggingface.co/sentence-transformers/all-mpnet-base-v2#:~:text=specification%20huggingface) sentence-transformers/all-mpnet-base-v2 · Hugging Face

[https://huggingface.co/sentence-transformers/all-mpnet-base-v2](https://huggingface.co/sentence-transformers/all-mpnet-base-v2)

[\[3\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=,which%20task%20is%20being%20performed) [\[4\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=Best%20Practices) [\[5\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=def%20mean_pooling,9) [\[6\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=For%20truncation%2C%20you%20can%20trucate,before%20applying%20normalization) [\[7\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=Best%20Practices) [\[8\]](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe#:~:text=,if%20storage%2Fcompute%20is%20a%20concern) nomic-ai/nomic-embed-text-v2-moe · Hugging Face

[https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe)

[\[9\]](https://bge-model.com/tutorial/1_Embedding/1.2.4.html#:~:text=Using%20BGE%20M3%20for%20dense,5%20models) [\[12\]](https://bge-model.com/tutorial/1_Embedding/1.2.4.html#:~:text=Using%20BGE%20M3%20for%20dense,5%20models) [\[14\]](https://bge-model.com/tutorial/1_Embedding/1.2.4.html#:~:text=2.2%20Sparse%20Retrieval) [\[15\]](https://bge-model.com/tutorial/1_Embedding/1.2.4.html#:~:text=2.3%20Multi) [\[16\]](https://bge-model.com/tutorial/1_Embedding/1.2.4.html#:~:text=2.4%20Hybrid%20Ranking) BGE-M3 — BGE documentation

[https://bge-model.com/tutorial/1\_Embedding/1.2.4.html](https://bge-model.com/tutorial/1_Embedding/1.2.4.html)

[\[10\]](https://bge-model.com/tutorial/1_Embedding/1.2.3.html#:~:text=Different%20from%20more%20commonly%20used,as%20the%20sentence%20embedding) BGE Explanation — BGE documentation

[https://bge-model.com/tutorial/1\_Embedding/1.2.3.html](https://bge-model.com/tutorial/1_Embedding/1.2.3.html)

[\[11\]](https://huggingface.co/BAAI/bge-m3#:~:text=Some%20suggestions%20for%20retrieval%20pipeline,in%20RAG) [\[13\]](https://huggingface.co/BAAI/bge-m3#:~:text=For%20embedding%20retrieval%2C%20you%20can,adding%20instructions%20to%20the%20queries) BAAI/bge-m3 · Hugging Face

[https://huggingface.co/BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)

[\[17\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=Model%20Dimensions%20Context%20MRL%20Quantization,32K%20Yes%20INT8%2FBINARY%20No%20Mean) [\[18\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=%3E%20%60pplx,compare%20them%20via%20cosine%20similarity) [\[19\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=%3E%20Currently%2C%20only%20int8,similarity%20with%20unnormalized%20int8%20embeddings) [\[20\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=All%20models%20are%20built%20on,trained%20Qwen3%20at%20Perplexity%20AI) [\[21\]](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b#:~:text=Model%20Dimensions%20Context%20MRL%20Quantization,32K%20Yes%20INT8%2FBINARY%20No%20Mean) perplexity-ai/pplx-embed-v1-0.6b · Hugging Face

[https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b)

[\[22\]](https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings#:~:text=All%20models%20use%20mean%20pooling,and%20require%20no%20instruction%20prefix) [\[23\]](https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings#:~:text=Basic%20Usage) [\[24\]](https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings#:~:text=Parameter%20Type%20Required%20Default%20Description,2560%20for%204b) Contextualized Embeddings \- Perplexity

[https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings](https://docs.perplexity.ai/docs/embeddings/contextualized-embeddings)