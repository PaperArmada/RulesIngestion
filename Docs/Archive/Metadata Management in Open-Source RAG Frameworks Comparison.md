# Metadata Management in Open‑Source RAG Frameworks

Retrieval‑augmented‑generation (RAG) systems rely on two core stages: ingestion and retrieval.  
**Metadata** refers to structured information attached to each text fragment (chunk) during ingestion, such as the source document, section title, page number, URL, or semantic tags.  
During retrieval the metadata enables filtering and ranking to ensure the model receives contextually relevant information.  
This report compares how prominent open‑source RAG frameworks—**LlamaIndex**, **LangChain**, **RAGFlow** and **Dify**—construct, store and leverage metadata and highlights common practices and standout ideas.

## Common philosophy across frameworks

Across all frameworks, metadata serves three purposes:

1. **Contextual anchoring** – Each chunk is linked back to its source (file, page, paragraph), making it possible to provide citations or navigate to the original rulebook.

2. **Filtering and disambiguation** – Metadata keys (e.g., category, department, edition, language) allow filtering of search results.

3. **Enhanced retrieval** – During query processing, metadata can be used to restrict the search space (only look at rulebooks of a certain edition) or re‑rank results (prioritise chunks from core rules).

All frameworks follow a similar pipeline:

* **Data loading** – Use file loaders for PDFs, HTML or plain text.

* **Chunking** – Split long documents into manageable chunks (e.g., by sentence or paragraph).

* **Metadata assignment** – Attach key‑value metadata to each chunk (source file, page number, chapter title, etc.).

* **Embedding \+ storage** – Generate vector embeddings and store them alongside metadata in a vector store or database.

* **Query and retrieval** – Generate an embedding for the user query, search the vector store, optionally filter on metadata, and return the top‑k results with their metadata.

## LlamaIndex

### Metadata extraction and storage

LlamaIndex (formerly GPT‑Index) offers detailed guidance on constructing ingestion pipelines:

* It loads documents using **readers** such as PyMuPDFReader for PDFs[\[1\]](https://developers.llamaindex.ai/python/examples/low_level/oss_ingestion_retrieval/#:~:text=1).

* A **text splitter** (e.g., SentenceSplitter) divides documents into chunks (default \~1024 tokens)[\[1\]](https://developers.llamaindex.ai/python/examples/low_level/oss_ingestion_retrieval/#:~:text=1).

* Each chunk is wrapped in a TextNode with metadata including page number, file name and other user‑defined fields[\[1\]](https://developers.llamaindex.ai/python/examples/low_level/oss_ingestion_retrieval/#:~:text=1).

* The ingestion script then computes embeddings and stores the nodes in a vector store such as Postgres (PGVectorStore)[\[1\]](https://developers.llamaindex.ai/python/examples/low_level/oss_ingestion_retrieval/#:~:text=1).

LlamaIndex emphasises that long documents can produce ambiguous chunks; to improve retrieval, it uses **LLM‑based metadata extraction**.  
For example, the *metadata‑extraction* module uses a language‑model prompt to generate a **context summary** for each chunk.  
This summary, stored as metadata, helps disambiguate chunks that might otherwise appear similar, improving retrieval quality when searching for overlapping topics.

### Retrieval

When processing a query, LlamaIndex’s retrieval pipeline performs these steps[\[2\]](https://developers.llamaindex.ai/python/examples/low_level/oss_ingestion_retrieval/#:~:text=):

1. Compute a query embedding.

2. Query the vector store for the k most similar nodes.

3. Return a list of NodeWithScore objects, including both the text and metadata.

4. Use a custom retriever class (VectorDBRetriever) to integrate retrieval into an agent or chain[\[2\]](https://developers.llamaindex.ai/python/examples/low_level/oss_ingestion_retrieval/#:~:text=).

**Stand‑out idea:** LlamaIndex’s metadata extraction leverages LLMs to generate additional context for each chunk.  
This helps disambiguate similar passages and reduces hallucination; the metadata becomes a *second layer of context*, not just factual data.

## LangChain

LangChain is a modular framework that supports RAG pipelines with many vector stores and models. Its **metadata philosophy** is explicitly demonstrated in the Metadata Filtering tutorial:

* Documents are represented by Document objects that include a page\_content string and a metadata dictionary[\[3\]](https://www.geeksforgeeks.org/artificial-intelligence/metadata-filtering-in-langchain/#:~:text=Python%20).

* Metadata can be any key‑value data (e.g., {"source":"report.pdf", "department":"finance", "year":2023})[\[4\]](https://www.geeksforgeeks.org/artificial-intelligence/metadata-filtering-in-langchain/#:~:text=Metadata%20filtering%20is%20a%20technique,as%20source%20or%20time%20period).

* When storing embeddings in a vector store like Chroma or FAISS, the metadata is stored alongside the vector[\[3\]](https://www.geeksforgeeks.org/artificial-intelligence/metadata-filtering-in-langchain/#:~:text=Python%20).

### Retrieval with metadata filtering

LangChain supports retrieving documents using a filter parameter.  
In the tutorial, vectorstore.similarity\_search accepts a filter dictionary such as {"department":"finance"} or more complex conditions like {"$and": \[{"year":{"$gt":2022}}, {"department":"finance"}\]}[\[5\]](https://www.geeksforgeeks.org/artificial-intelligence/metadata-filtering-in-langchain/#:~:text=%2A%20Chroma%20supports%20metadata,specific%20source%2C%20year%20and%20category).  
Only documents whose metadata match the filter are returned.  
This allows queries such as “find documents about taxes in 2023 and later” to be answered without scanning all vectors.

**Stand‑out ideas:**  
\- **Declarative filtering**: The ability to specify complex logical predicates ($and, $or, $gt, $lt) on metadata makes fine‑grained retrieval straightforward[\[5\]](https://www.geeksforgeeks.org/artificial-intelligence/metadata-filtering-in-langchain/#:~:text=%2A%20Chroma%20supports%20metadata,specific%20source%2C%20year%20and%20category).  
\- **Separation of concerns**: Metadata filtering is decoupled from embedding similarity; the vector store first filters by metadata, then ranks by similarity.

## RAGFlow

RAGFlow is an open‑source framework that combines data ingestion, index building and agent orchestration.  
The project emphasises a **built‑in ingestion pipeline** that “cleanses and processes multi‑format data, structuring it into rich semantic representations for superior retrieval”[\[6\]](https://ragflow.io/#:~:text=ETL%20for%20AI%20data).  
Key aspects:

* **Multi‑format ingestion**: RAGFlow aims to ingest PDFs, webpages and other data types, normalising them into a unified representation.

* **Hybrid search**: It supports hybrid retrieval (dense \+ sparse) so metadata (sparse lexical features like term frequencies) and embeddings (dense semantics) both contribute.

* **Structured metadata**: While the documentation does not provide step‑by‑step code, the description suggests that the ingestion pipeline extracts metadata such as file type, date and domain and associates it with each chunk[\[6\]](https://ragflow.io/#:~:text=ETL%20for%20AI%20data).

**Stand‑out idea:**  
RAGFlow’s ingestion pipeline emphasises **data cleansing and normalisation** so that both text and metadata are harmonised across sources.  
Its hybrid retrieval indicates a design where **metadata is indexed in a sparse manner** (e.g., inverted index) alongside dense embeddings; this helps recall rare keywords or exact terms when necessary.

## Dify

Dify is a low‑code platform for building AI apps with RAG. According to a 2026 overview of open‑source frameworks, Dify includes **a visual workflow builder** that lets users design RAG pipelines via drag‑and‑drop[\[7\]](https://www.firecrawl.dev/blog/best-open-source-rag-frameworks#:~:text=Dify%20is%20an%20open,ready%20AI%20applications).  
While metadata details are not deeply documented, Dify’s design implies:

* **Workflow orchestration**: Users can insert nodes for loading, splitting, embedding and indexing. Each node can attach metadata or transform it (e.g., extract chapter names).

* **Evaluation tools**: Dify provides evaluation and monitoring tools to measure retrieval accuracy[\[7\]](https://www.firecrawl.dev/blog/best-open-source-rag-frameworks#:~:text=Dify%20is%20an%20open,ready%20AI%20applications), suggesting that metadata is leveraged to compute metrics (e.g., retrieving from the correct chapter).

**Stand‑out idea:**  
Dify uses a **visual interface** to structure the ingestion pipeline. This lowers the barrier for non‑developers to configure metadata extraction and filters without coding; such an interface may inspire custom pipelines for tabletop rulebooks.

## Comparison of metadata practices

| Framework | Metadata creation and storage | Use in retrieval | Stand‑out features |
| :---- | :---- | :---- | :---- |
| **LlamaIndex** | Chunks are wrapped in TextNode with metadata; optional **LLM‑based metadata extraction** generates a summary per chunk to help disambiguate context[\[1\]](https://developers.llamaindex.ai/python/examples/low_level/oss_ingestion_retrieval/#:~:text=1). | Query embedding used to fetch top‑k; metadata returned with results; LLM‑generated summaries improve relevance; retrieval classes can also apply metadata filters or hierarchical retrieval. | Uses LLMs to generate contextual metadata, reducing confusion between similar passages. |
| **LangChain** | Documents store arbitrary key‑value metadata (source, year, department)[\[3\]](https://www.geeksforgeeks.org/artificial-intelligence/metadata-filtering-in-langchain/#:~:text=Python%20); stored alongside vectors. | Retrieval functions support a filter dictionary with logical operators ($and, $gt$ etc.) to restrict candidates[\[5\]](https://www.geeksforgeeks.org/artificial-intelligence/metadata-filtering-in-langchain/#:~:text=%2A%20Chroma%20supports%20metadata,specific%20source%2C%20year%20and%20category). | Declarative metadata filtering; decouples filtering from similarity; integrates with many stores and models. |
| **RAGFlow** | Built‑in ingestion pipeline cleanses multi‑format data and attaches semantic metadata[\[6\]](https://ragflow.io/#:~:text=ETL%20for%20AI%20data). | Hybrid retrieval leverages both embeddings and lexical metadata; details limited. | Focus on multi‑format ingestion and hybrid search; emphasises data cleaning. |
| **Dify** | Visual workflow builder allows adding metadata steps; specifics not fully documented[\[7\]](https://www.firecrawl.dev/blog/best-open-source-rag-frameworks#:~:text=Dify%20is%20an%20open,ready%20AI%20applications). | Likely supports filters and evaluation using metadata; UI helps configure retrieval parameters. | Low‑code interface for pipeline design and evaluation. |

## Takeaways and recommendations

* **Always attach granular metadata** – For TTRPG rulebooks, include book name, edition, chapter, page number, creature/spell names and unique IDs. This enables retrieval filtered to a particular rulebook or edition.

* **Consider LLM‑generated context** – LlamaIndex’s approach of summarising each chunk can reduce ambiguity when spells or creatures have similar names; this may be useful when multiple spells share keywords (e.g., *Summon Elemental* vs *Conjure Elemental*).

* **Use metadata filtering** – Follow LangChain’s pattern of specifying filters (e.g., {"edition":"5e", "section":"combat"}) to restrict retrieval. Provide support for logical operators to handle range queries (e.g., level ≥ 3).

* **Hybrid retrieval** – Adopt RAGFlow’s idea of combining dense embeddings with sparse lexical indices. Metadata keys (e.g., names, tags) can be indexed lexically and combined with dense scores to improve recall.

* **User‑friendly tools** – Dify demonstrates that a UI can lower entry barriers. Consider building a simple interface for customizing metadata fields and retrieval strategies, enabling domain experts (game masters) to adjust pipelines without coding.

By studying these frameworks, we can design a robust ingestion pipeline for TTRPG rulebooks where each chunk is richly annotated with context, stored alongside its embedding, and efficiently retrievable using both semantic similarity and metadata filters. Such metadata‑driven design will ensure accurate, explainable answers and easier maintenance as new rulebooks or editions are added.

---

[\[1\]](https://developers.llamaindex.ai/python/examples/low_level/oss_ingestion_retrieval/#:~:text=1) [\[2\]](https://developers.llamaindex.ai/python/examples/low_level/oss_ingestion_retrieval/#:~:text=) Building RAG from Scratch (Open-source only\!) | LlamaIndex Python Documentation

[https://developers.llamaindex.ai/python/examples/low\_level/oss\_ingestion\_retrieval/](https://developers.llamaindex.ai/python/examples/low_level/oss_ingestion_retrieval/)

[\[3\]](https://www.geeksforgeeks.org/artificial-intelligence/metadata-filtering-in-langchain/#:~:text=Python%20) [\[4\]](https://www.geeksforgeeks.org/artificial-intelligence/metadata-filtering-in-langchain/#:~:text=Metadata%20filtering%20is%20a%20technique,as%20source%20or%20time%20period) [\[5\]](https://www.geeksforgeeks.org/artificial-intelligence/metadata-filtering-in-langchain/#:~:text=%2A%20Chroma%20supports%20metadata,specific%20source%2C%20year%20and%20category) Metadata Filtering in LangChain \- GeeksforGeeks

[https://www.geeksforgeeks.org/artificial-intelligence/metadata-filtering-in-langchain/](https://www.geeksforgeeks.org/artificial-intelligence/metadata-filtering-in-langchain/)

[\[6\]](https://ragflow.io/#:~:text=ETL%20for%20AI%20data) RAGFlow

[https://ragflow.io/](https://ragflow.io/)

[\[7\]](https://www.firecrawl.dev/blog/best-open-source-rag-frameworks#:~:text=Dify%20is%20an%20open,ready%20AI%20applications) 15 Best Open-Source RAG Frameworks in 2026

[https://www.firecrawl.dev/blog/best-open-source-rag-frameworks](https://www.firecrawl.dev/blog/best-open-source-rag-frameworks)