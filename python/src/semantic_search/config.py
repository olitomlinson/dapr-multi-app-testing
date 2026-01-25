"""
Configuration and global instances for the Hello World app.
"""
import dapr.ext.workflow as wf
from .workflow_manager import WorkflowRuntimeManager

# Global workflow runtime instance - shared across all workflows
workflow_runtime = wf.WorkflowRuntime()

# Import activity definitions to ensure they are registered
from . import activities

# Global workflow runtime manager instance - handles lifecycle management
workflow_runtime_manager = WorkflowRuntimeManager(workflow_runtime)
