"""
Semantic search workflow using GPU-accelerated embeddings and similarity computation.

This workflow demonstrates how Python orchestrates business logic while delegating
GPU-intensive ML computations to activities via Dapr workflows.
"""
import logging
from dataclasses import dataclass
from typing import List, Optional
from ..config import workflow_runtime
from datetime import timedelta

logger = logging.getLogger(__name__)


@dataclass
class SemanticSearchInput:
    """Input payload for semantic search workflow."""
    query: str
    documents: List[str]
    model_name: Optional[str] = None
    sandbag_seconds: Optional[int] = None


@dataclass
class DocumentScore:
    """Result for a single document's similarity to the query."""
    document: str
    similarity: float
    interpretation: str


@dataclass
class SemanticSearchOutput:
    """Output from semantic search workflow."""
    query: str
    results: List[DocumentScore]
    device: str
    total_processing_time_ms: float
    embedding_dimension: int


@workflow_runtime.workflow(name='semantic_search_workflow')
def semantic_search_workflow(ctx, input_data: dict) -> dict:
    """
    Workflow demonstrating GPU-accelerated semantic search using Python activities.

    This workflow shows how to orchestrate business logic while delegating
    GPU-intensive ML computations to Python activities via Dapr workflow.

    Args:
        ctx: Workflow context
        input_data: Dictionary containing query, documents, optional model_name and sandbag_seconds

    Returns:
        Dictionary containing query, results, device, performance metrics
    """
    workflow_id = ctx.instance_id

    # Parse input
    query = input_data.get("query", "")
    documents = input_data.get("documents", [])
    model_name = input_data.get("model_name")
    sandbag_seconds = input_data.get("sandbag_seconds")

    logger.info(f"[workflow={workflow_id}] Starting semantic search for query: '{query}'")

    # Step 1: Generate embedding for the query
    logger.info(f"[workflow={workflow_id}] Generating query embedding...")

    query_embedding_request = {
        "texts": [query],
        "normalize": True,
        "model_name": model_name,
        "sandbag_seconds": sandbag_seconds
    }

    # yield ctx.create_timer(fire_at=timedelta(seconds=5))


    query_embedding_response = yield ctx.call_activity(
        "generate_embeddings",
        input=query_embedding_request,
        app_id='dotnet'
    )

    # Convert to dict if it's a SimpleNamespace
    if not isinstance(query_embedding_response, dict):
        query_embedding_response = vars(query_embedding_response)

    logger.info(
        f"[workflow={workflow_id}] Query embedding generated on {query_embedding_response['device']} "
        f"in {query_embedding_response['processing_time_ms']:.2f}ms"
    )

    # Step 2: Generate embeddings for all documents in batch
    logger.info(f"[workflow={workflow_id}] Generating embeddings for {len(documents)} documents...")

    documents_embedding_request = {
        "texts": documents,
        "normalize": True,
        "model_name": model_name
    }

    documents_embedding_response = yield ctx.call_activity(
        "generate_embeddings",
        input=documents_embedding_request,
        app_id='dotnet'
    )

    # Convert to dict if it's a SimpleNamespace
    if not isinstance(documents_embedding_response, dict):
        documents_embedding_response = vars(documents_embedding_response)

    logger.info(
        f"[workflow={workflow_id}] Document embeddings generated on {documents_embedding_response['device']} "
        f"in {documents_embedding_response['processing_time_ms']:.2f}ms"
    )

    # Step 3: Compute similarity scores for each document
    logger.info(f"[workflow={workflow_id}] Computing similarity scores...")

    query_embedding = query_embedding_response["embeddings"][0]
    results = []

    for i, document in enumerate(documents):
        doc_embedding = documents_embedding_response["embeddings"][i]

        similarity_request = {
            "embeddings1": query_embedding,
            "embeddings2": doc_embedding
        }

        similarity_response = yield ctx.call_activity(
            "compute_similarity",
            input=similarity_request,
            app_id='dotnet'
        )

        # Convert to dict if it's a SimpleNamespace
        if not isinstance(similarity_response, dict):
            similarity_response = vars(similarity_response)

        results.append({
            "document": document,
            "similarity": similarity_response["similarity"],
            "interpretation": similarity_response["interpretation"]
        })

    # Sort by similarity (highest first)
    results = sorted(results, key=lambda x: x["similarity"], reverse=True)

    total_time = (
        query_embedding_response["processing_time_ms"] +
        documents_embedding_response["processing_time_ms"]
    )

    output = {
        "query": query,
        "results": results,
        "device": documents_embedding_response["device"],
        "total_processing_time_ms": total_time,
        "embedding_dimension": documents_embedding_response["dimension"]
    }

    logger.info(
        f"[workflow={workflow_id}] Semantic search complete. Best match: '{results[0]['document']}' "
        f"(similarity: {results[0]['similarity']:.4f})"
    )

    return output
