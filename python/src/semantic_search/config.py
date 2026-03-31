"""
Configuration and global instances for the Hello World app.
"""
import dapr.ext.workflow as wf
from .workflow_manager import WorkflowRuntimeManager

# Global workflow runtime instance - shared across all workflows
workflow_runtime = wf.WorkflowRuntime()

# Import activity definitions individually to ensure they are registered
from .activities import generate_embeddings, compute_similarity

# Import workflow definitions to ensure they are registered
from .workflows import semantic_search_workflow

# Global workflow runtime manager instance - handles lifecycle management
workflow_runtime_manager = WorkflowRuntimeManager(workflow_runtime)
