"""
Garcar Enterprise — Hugging Face Integration
AI inference for lead scoring, deal classification, and code review.
Models served via HF Inference Endpoints + hub API.
"""
import os
from huggingface_hub import InferenceClient
from event_bus_sdk import ButlerEventBus

bus = ButlerEventBus()

client = InferenceClient(token=os.environ["HUGGINGFACE_API_TOKEN"])

MODELS = {
    "lead_scorer": os.environ.get("HF_LEAD_SCORER_MODEL", "Garrettc123/lead-scoring-model"),
    "deal_classifier": os.environ.get("HF_DEAL_CLASSIFIER_MODEL", "Garrettc123/deal-pipeline-classifier"),
    "embedder": "sentence-transformers/all-MiniLM-L6-v2",
    "code_reviewer": "bigcode/starcoder2-7b"
}

async def score_lead(lead_data: dict) -> dict:
    """Score a lead from lead-enrichment-engine output using HF model."""
    prompt = f"Lead: {lead_data.get('company', '')} | Title: {lead_data.get('title', '')} | Source: {lead_data.get('source', '')}"
    try:
        result = client.text_classification(prompt, model=MODELS["lead_scorer"])
        score = result[0]["score"] if result else 0.5
        label = result[0]["label"] if result else "MEDIUM"
    except Exception:
        score, label = 0.5, "UNKNOWN"
    
    enriched = {**lead_data, "hf_score": score, "hf_label": label}
    await bus.emit("lead.scored", enriched, agents=["RevenueOpsAgent"])
    return enriched

async def embed_document(text: str) -> list:
    """Generate embeddings for Supabase vector search."""
    result = client.feature_extraction(text, model=MODELS["embedder"])
    return result[0] if result else []

async def review_code_diff(diff: str) -> str:
    """AI code review on PR diffs — triggered by GitHub webhook."""
    prompt = f"Review this code diff and identify issues:\n\n{diff[:2000]}"
    result = client.text_generation(prompt, model=MODELS["code_reviewer"], max_new_tokens=500)
    return result

# Subscribe to lead enrichment events
async def handle_lead_enriched(event):
    await score_lead(event)

bus.subscribe("lead.enriched", handle_lead_enriched)
