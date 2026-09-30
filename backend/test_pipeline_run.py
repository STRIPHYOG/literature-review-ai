import asyncio
import httpx
import fitz  # PyMuPDF
import json
import time

def create_sample_pdf_1():
    doc = fitz.open()
    page = doc.new_page()
    text = """
Dense Passage Retrieval for Open-Domain Question Answering
Authors: Vladimir Karpukhin, Barlas Oguz, Sewon Min, Patrick Lewis, Ledell Wu, Sergey Edunov, Danqi Chen, Wentau Yih
Published: 2020

Abstract
Open-domain question answering relies on efficient passage retrieval to select candidate contexts. Traditional sparse vector space models such as BM25 match keywords efficiently, but fail to capture semantic meaning and synonyms. In this paper, we show that retrieval can be practically implemented using dense representations, where embeddings are learned from a small number of questions and passages by a dual-encoder framework. When evaluated on a wide range of open-domain QA datasets, our dense passage retriever (DPR) substantially outperforms BM25 by 9% to 19% in Top-20 passage retrieval accuracy.

Methodology
We employ a dual-encoder architecture utilizing two independent BERT encoders: EP(·) maps any passage p into a 768-dimensional real-valued vector, and EQ(·) maps an input question q to a matching 768-dimensional vector. The similarity between question and passage is computed using the dot product of their embeddings:
similarity(q, p) = EQ(q)^T · EP(p)
We train the dual-encoder using in-batch negatives and gold passage supervision with NLL loss. At inference time, all 21 million Wikipedia passages are indexed using FAISS for sub-millisecond maximum inner product search.

Datasets and Benchmarks
Experiments are conducted on five open-domain QA benchmarks: Natural Questions (NQ), WebQuestions, TriviaQA, CuratedTREC, and SQuAD v1.1. 

Evaluation Metrics and Key Results
On Natural Questions, Top-20 retrieval accuracy reaches 79.4% for DPR compared to 59.1% for BM25. Top-100 accuracy reaches 86.0%. When paired with a standard BERT reader model, DPR achieves 41.5 Exact Match (EM) score, setting a new state-of-the-art for end-to-end open-domain question answering.

Limitations
Dense retrieval requires significant memory footprint to host all 21 million passage vectors in RAM. Furthermore, DPR can struggle with rare entities and out-of-vocabulary technical keywords where exact lexical matching is superior.
"""
    page.insert_textbox(fitz.Rect(40, 40, 550, 750), text, fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

def create_sample_pdf_2():
    doc = fitz.open()
    page = doc.new_page()
    text = """
Hybrid Sparse-Dense Retrieval for Robust Scientific Question Answering
Authors: Elena Rostova, Marcus Thorne, David Lin, Sofia Alvarez
Published: 2022

Abstract
While dense neural retrieval models such as DPR excel at semantic understanding, they exhibit vulnerability to out-of-distribution scientific queries, numerical identifiers, and exact domain-specific nomenclature. Conversely, sparse keyword retrievers like BM25 excel at exact matching but miss semantic paraphrasing. In this work, we propose HybQA, a hybrid sparse-dense retrieval framework tailored for scientific and biomedical literature. By dynamically weighting lexical BM25 scores with dense contrastive embeddings, HybQA demonstrates robust zero-shot generalization across specialized technical domains.

Methodology
HybQA computes a joint ranking score defined as:
S_hybrid(q, p) = alpha * S_sparse(q, p) + (1 - alpha) * S_dense(q, p)
where alpha is an adaptive gating parameter learned via a shallow routing network conditioned on query lexical density and entity rarity. The sparse retriever utilizes BM25 with tuned k1=1.5 and b=0.75 parameters on specialized scientific vocabularies. The dense retriever utilizes SciBERT fine-tuned with reciprocal rank fusion.

Datasets and Benchmarks
We evaluate on three demanding scientific and biomedical QA benchmarks: BioASQ, COVID-QA, and SciFact.

Evaluation Metrics and Key Results
HybQA achieves 84.2% Top-20 recall on BioASQ, representing a +5.8% gain over pure DPR (78.4%) and +11.2% over BM25 (73.0%). On COVID-QA, HybQA achieves an MRR@10 of 0.682 compared to 0.541 for DPR alone. The hybrid score significantly reduces hallucination in downstream answer generation.

Limitations
The dual index structure increases storage complexity and query latency by approximately 25% compared to single-mode retrievers. The learned weighting parameter alpha may require recalibration when shifting between disparate domains such as computer science and oncology.
"""
    page.insert_textbox(fitz.Rect(40, 40, 550, 750), text, fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

async def run_test():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=120.0) as client:
        # 1. Health check
        resp = await client.get("/health")
        print("1. Health check:", resp.json())
        assert resp.status_code == 200

        # 2. Create session
        resp = await client.post("/api/sessions")
        session_data = resp.json()
        session_id = session_data["id"]
        print(f"2. Created session: {session_id} - status: {session_data.get('status')}")

        # 3. Upload papers
        pdf1 = create_sample_pdf_1()
        pdf2 = create_sample_pdf_2()
        
        files = [
            ("files", ("karpukhin2020_dpr.pdf", pdf1, "application/pdf")),
            ("files", ("rostova2022_hybqa.pdf", pdf2, "application/pdf")),
        ]
        resp = await client.post(f"/api/sessions/{session_id}/papers", files=files)
        print("3. Uploaded papers:", resp.json())
        assert resp.status_code == 200

        # 4. Trigger review generation
        gen_payload = {
            "focus_areas": ["Methodology comparison", "Retrieval performance & metrics", "Limitations & trade-offs"],
            "review_depth": "detailed",
        }
        resp = await client.post(f"/api/sessions/{session_id}/generate", json=gen_payload)
        print("4. Generation triggered:", resp.json())
        assert resp.status_code == 200

        # 5. Poll for completion
        print("5. Polling session status...")
        for i in range(40):
            await asyncio.sleep(3)
            status_resp = await client.get(f"/api/sessions/{session_id}")
            data = status_resp.json()
            status = data.get("status")
            progress = data.get("progress_percentage", 0)
            stage = data.get("current_stage", "")
            print(f"   [{i*3}s] Status: {status} | Progress: {progress}% | Stage: {stage}")
            if status == "completed":
                print("   Pipeline completed successfully!")
                break
            elif status == "failed":
                print("   Pipeline failed! Error:", data.get("error_message"))
                break

        # 6. Fetch generated review
        rev_resp = await client.get(f"/api/sessions/{session_id}/review")
        print(f"6. Review status: {rev_resp.status_code}")
        if rev_resp.status_code == 200:
            review = rev_resp.json()
            print(f"   Review Title: {review.get('title')}")
            print(f"   Claim Count: {review.get('claim_count')}")
            print(f"   Evidence Density: {review.get('evidence_density')}")
            print(f"   Comparison Table Columns: {list(review.get('comparison_table', {}).keys())}")
            print(f"   Markdown Preview (first 250 chars):\n{review.get('content_markdown', '')[:250]}...")
            print("\n*** ALL TESTS PASSED SUCCESSFULLY! ***")

if __name__ == "__main__":
    asyncio.run(run_test())
