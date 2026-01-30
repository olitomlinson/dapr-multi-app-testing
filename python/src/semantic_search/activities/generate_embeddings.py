"""
Activity for generating text embeddings using GPU-accelerated transformers.

This activity demonstrates using Python for GPU-intensive ML workloads
while .NET orchestrates the business logic via Dapr workflows.
"""
import logging
import time
from dataclasses import dataclass
from typing import List, Optional
from ..config import workflow_runtime

logger = logging.getLogger(__name__)

# Global model cache (lazy loaded, supports multiple models)
_models = {}
_default_model_name = "all-MiniLM-L6-v2"  # Fast, efficient sentence transformer


def _get_model(model_name: Optional[str] = None):
    """
    Lazy load the sentence transformer model.

    Args:
        model_name: Name of the model to load. If None, uses default.

    Returns:
        Loaded SentenceTransformer model
    """
    global _models

    # Use default if not specified
    if not model_name:
        model_name = _default_model_name

    # Return cached model if already loaded
    if model_name in _models:
        logger.debug(f"Using cached model: {model_name}")
        return _models[model_name]

    # Load new model
    try:
        from sentence_transformers import SentenceTransformer
        import torch

        # Select best available device before loading
        if torch.backends.mps.is_available():
            device = "mps"  # Apple Silicon GPU (M1/M2/M3)
            logger.info("Loading model on device: mps (Apple Silicon GPU)")
        elif torch.cuda.is_available():
            device = "cuda"  # NVIDIA GPU
            logger.info(f"Loading model on device: cuda (NVIDIA GPU: {torch.cuda.get_device_name(0)})")
        else:
            device = "cpu"
            logger.info("Loading model on device: cpu (no GPU available)")

        # Load model directly on target device
        logger.info(f"Loading sentence transformer model: {model_name}")
        model = SentenceTransformer(model_name, device=device)
        logger.info(f"Model {model_name} successfully loaded on {device}")

        # Cache the model
        _models[model_name] = model
        return model

    except ImportError as e:
        logger.error(f"Failed to import required libraries: {e}")
        raise RuntimeError(
            "sentence-transformers not installed. "
            "Install with: pip install sentence-transformers torch"
        )
    except Exception as e:
        logger.error(f"Failed to load model {model_name}: {e}")
        raise RuntimeError(f"Could not load model {model_name}: {str(e)}")


@dataclass
class EmbeddingRequest:
    """Request for text embedding generation."""
    texts: List[str]
    normalize: bool = True
    model_name: Optional[str] = None
    sandbag_seconds: Optional[int] = None


@dataclass
class EmbeddingResponse:
    """Response containing embeddings and metadata."""
    embeddings: List[List[float]]
    model_name: str
    device: str
    dimension: int
    processing_time_ms: float
    num_texts: int


@workflow_runtime.activity(name='generate_embeddings')
def generate_embeddings(_ctx, input_data: dict) -> EmbeddingResponse:
    """
    Generate text embeddings using GPU-accelerated transformer models.

    Args:
        _ctx: Activity context
        input_data: Dictionary with 'texts' (list of strings), optional 'normalize' (bool),
                   and optional 'model_name' (str)

    Returns:
        EmbeddingResponse with embeddings and performance metrics
    """
    start_time = time.time()

    # Extract workflow and activity IDs for logging
    workflow_id = getattr(_ctx, 'workflow_id', 'unknown')
    activity_id = getattr(_ctx, 'task_id', 'unknown')

    # Construct request from dict
    request = EmbeddingRequest(
        texts=input_data.get("texts", []),
        normalize=input_data.get("normalize", True),
        model_name=input_data.get("model_name"),
        sandbag_seconds=input_data.get("sandbag_seconds")
    )

    # Inject artificial delay if sandbag_seconds is set (dev mode)
    if request.sandbag_seconds and request.sandbag_seconds > 0:
        logger.warning(
            f"[workflow={workflow_id}, activity={activity_id}] "
            f"🐌 SANDBAG MODE: Sleeping for {request.sandbag_seconds} seconds before processing "
            f"(artificial delay for testing)"
        )
        time.sleep(request.sandbag_seconds)
        logger.info(
            f"[workflow={workflow_id}, activity={activity_id}] "
            f"Sandbag delay complete, proceeding with embedding generation"
        )

    # Determine which model to use
    model_name = request.model_name or _default_model_name

    if not request.texts:
        logger.warning(f"[workflow={workflow_id}, activity={activity_id}] Empty text list provided")
        return EmbeddingResponse(
            embeddings=[],
            model_name=model_name,
            device="none",
            dimension=0,
            processing_time_ms=0.0,
            num_texts=0
        )

    logger.info(
        f"[workflow={workflow_id}, activity={activity_id}] "
        f"Generating embeddings for {len(request.texts)} text(s) using model: {model_name}"
    )

    try:
        import torch

        # Get model (will load if not cached)
        model = _get_model(model_name)

        # Determine which device is being used
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"

        # Generate embeddings
        embeddings = model.encode(
            request.texts,
            normalize_embeddings=request.normalize,
            convert_to_tensor=False  # Return as numpy arrays
        )

        # Convert to list of lists for JSON serialization
        embeddings_list = [emb.tolist() for emb in embeddings]

        processing_time = (time.time() - start_time) * 1000  # Convert to ms

        logger.info(
            f"[workflow={workflow_id}, activity={activity_id}] "
            f"Generated {len(embeddings_list)} embeddings using {model_name} "
            f"(dim={len(embeddings_list[0])}) in {processing_time:.2f}ms on {device}"
        )

        return EmbeddingResponse(
            embeddings=embeddings_list,
            model_name=model_name,
            device=device,
            dimension=len(embeddings_list[0]) if embeddings_list else 0,
            processing_time_ms=processing_time,
            num_texts=len(request.texts)
        )

    except Exception as e:
        logger.error(f"[workflow={workflow_id}, activity={activity_id}] Error generating embeddings: {e}")
        raise
