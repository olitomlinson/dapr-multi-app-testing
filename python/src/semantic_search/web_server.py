"""
FastAPI web server for the Hello World app.
"""
import asyncio
import json
import logging
import uuid
from typing import Dict, List, Optional
from functools import lru_cache

import uvicorn
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import dapr.ext.workflow as wf

from .workflows.semantic_search_workflow import semantic_search_workflow

logger = logging.getLogger(__name__)


@lru_cache()
def get_workflow_client() -> wf.DaprWorkflowClient:
    """Get cached DaprWorkflowClient instance for dependency injection."""
    return wf.DaprWorkflowClient()


class GreetingRequest(BaseModel):
    """Request model for greeting endpoint."""
    name: str


class SemanticSearchRequest(BaseModel):
    """Request model for semantic search endpoint."""
    query: str
    documents: List[str]
    model_name: Optional[str] = None
    sandbag_seconds: Optional[int] = None
    workflow_name: Optional[str] = None


class WebServer:
    """
    FastAPI web server for the Hello World app.

    Provides REST API endpoints to trigger Dapr workflows.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """
        Initialize the web server.

        Args:
            host: Server host address
            port: Server port number
        """
        self.host = host
        self.port = port
        self.app = create_app()
        self.server = None

    async def start(self) -> None:
        """Start the FastAPI server."""
        try:
            config = uvicorn.Config(
                app=self.app,
                host=self.host,
                port=self.port,
                log_level="info"
            )
            self.server = uvicorn.Server(config)
            logger.info(f"Starting web server on {self.host}:{self.port}")
            await self.server.serve()

        except Exception as e:
            logger.error(f"Failed to start web server: {e}")
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop the FastAPI server."""
        try:
            if self.server:
                logger.info("Stopping web server")
                self.server.should_exit = True

        except Exception as e:
            logger.error(f"Error during web server shutdown: {e}")

    def run(self) -> None:
        """Run the server (blocking)."""
        uvicorn.run(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        FastAPI: Configured FastAPI application
    """
    app = FastAPI(
        title="Semantic Search Dapr Workflow API",
        description="FastAPI app with Dapr workflow integration for semantic search",
        version="0.1.0",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins for development
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_model=Dict[str, str])
    async def root():
        """Root endpoint providing API information."""
        return {
            "message": "Hello World Dapr Workflow API",
            "version": "0.1.0",
            "status": "running"
        }

    @app.get("/health", response_model=Dict[str, str])
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    @app.get("/workflow/{instance_id}")
    async def get_workflow_status(
        instance_id: str,
        wf_client: wf.DaprWorkflowClient = Depends(get_workflow_client)
    ):
        """
        Get the status of a running or completed workflow.

        Returns the current state and output (if completed) of a workflow instance.
        """
        try:
            logger.info(f"Checking status for workflow: {instance_id}")

            # Get workflow state
            state = wf_client.get_workflow_state(instance_id=instance_id, fetch_payloads=True)

            response_data = {
                "workflow_instance_id": instance_id,
                "runtime_status": state.runtime_status.name if state.runtime_status else "UNKNOWN",
                "created_at": state.created_at.isoformat() if state.created_at else None,
                "last_updated_at": state.last_updated_at.isoformat() if state.last_updated_at else None,
            }

            # Add output if workflow is completed
            if state.runtime_status and state.runtime_status.name == "COMPLETED":
                response_data["output"] = json.loads(state.serialized_output) if state.serialized_output else None

            # Add failure details if workflow failed
            if state.runtime_status and state.runtime_status.name == "FAILED":
                response_data["failure_details"] = state.serialized_output

            return JSONResponse(
                status_code=200,
                content=response_data
            )

        except Exception as e:
            logger.error(f"Failed to get workflow status: {str(e)}")
            return JSONResponse(
                status_code=404,
                content={"error": f"Workflow not found or error retrieving status: {str(e)}"}
            )

    @app.get("/semantic-search/workflow/{instance_id}")
    async def get_semantic_search_workflow_status(
        instance_id: str,
        wf_client: wf.DaprWorkflowClient = Depends(get_workflow_client)
    ):
        """
        Get the status of a semantic search workflow (matches .NET endpoint structure).

        Returns the current state and output (if completed) of a workflow instance.
        """
        try:
            logger.info(f"Checking semantic search workflow status: {instance_id}")

            # Get workflow state
            state = wf_client.get_workflow_state(instance_id=instance_id, fetch_payloads=True)

            status_name = state.runtime_status.name if state.runtime_status else "UNKNOWN"

            response_data = {
                "workflowId": instance_id,
                "status": status_name,
                "createdAt": state.created_at.isoformat() if state.created_at else None,
                "lastUpdatedAt": state.last_updated_at.isoformat() if state.last_updated_at else None,
            }

            # Add output if workflow is completed
            if status_name == "COMPLETED" and state.serialized_output:
                output_data = json.loads(state.serialized_output)
                response_data["output"] = output_data

            # Add failure details if workflow failed
            if status_name == "FAILED":
                response_data["failureDetails"] = state.serialized_output

            return JSONResponse(
                status_code=200,
                content=response_data
            )

        except Exception as e:
            logger.error(f"Failed to get semantic search workflow status: {str(e)}")
            return JSONResponse(
                status_code=404,
                content={"error": f"Workflow not found or error retrieving status: {str(e)}"}
            )

    def send_sse_event(event_type: str, data: dict) -> str:
        """
        Format data as Server-Sent Event.

        Args:
            event_type: Type of event (scheduled, started, result, error, heartbeat)
            data: Data payload to send

        Returns:
            Formatted SSE message
        """
        json_data = json.dumps(data)
        return f"event: {event_type}\ndata: {json_data}\n\n"

    @app.post("/semantic-search/stream")
    async def semantic_search_stream(
        request_data: SemanticSearchRequest,
        wf_client: wf.DaprWorkflowClient = Depends(get_workflow_client)
    ):
        """
        Execute semantic search workflow with Server-Sent Events streaming.

        This endpoint streams workflow progress events to the client in real-time,
        including scheduled, started, heartbeat, result, and error events.
        """
        workflow_id = f"semantic-search-{str(uuid.uuid4())[:8]}"

        async def event_generator():
            try:
                logger.info(f"Starting SSE semantic search workflow with query: '{request_data.query}'")

                # Prepare workflow input
                workflow_input = {
                    "query": request_data.query,
                    "documents": request_data.documents,
                    "model_name": request_data.model_name,
                    "sandbag_seconds": request_data.sandbag_seconds
                }

                # Schedule the workflow
                workflow_name = request_data.workflow_name or "semantic_search_workflow"
                logger.info(f"Scheduling workflow '{workflow_name}' with ID: {workflow_id}")
                instance_id = wf_client.schedule_new_workflow(
                    workflow=semantic_search_workflow,
                    instance_id=workflow_id,
                    input=workflow_input
                )

                # Send scheduled event
                yield send_sse_event("scheduled", {
                    "workflowId": instance_id,
                    "query": request_data.query,
                    "numDocuments": len(request_data.documents),
                    "modelName": request_data.model_name
                })

                # Wait for workflow to start (run in thread to avoid blocking)
                await asyncio.to_thread(wf_client.wait_for_workflow_start, instance_id)

                # Send started event
                yield send_sse_event("started", {
                    "workflowId": instance_id
                })

                # Poll workflow status and send heartbeats
                heartbeat_interval = 15.0  # seconds
                last_heartbeat = asyncio.get_event_loop().time()

                while True:
                    try:
                        # Check if we should send a heartbeat
                        current_time = asyncio.get_event_loop().time()
                        if current_time - last_heartbeat >= heartbeat_interval:
                            yield send_sse_event("heartbeat", {
                                "workflowId": workflow_id,
                                "timestamp": current_time
                            })
                            last_heartbeat = current_time

                        # Check workflow state
                        state = wf_client.get_workflow_state(instance_id, fetch_payloads=True)

                        if state.runtime_status.name in ["COMPLETED", "FAILED", "TERMINATED"]:
                            break

                        # Wait a bit before next check
                        await asyncio.sleep(0.5)

                    except Exception as e:
                        logger.error(f"Error checking workflow state: {e}")
                        break

                # Check if workflow completed successfully
                if state.runtime_status.name == "COMPLETED":
                    result = json.loads(state.serialized_output)

                    logger.info(
                        f"SSE Semantic search completed. Device: {result.get('device')}, "
                        f"Time: {result.get('total_processing_time_ms')}ms"
                    )

                    # Send final result
                    yield send_sse_event("result", {
                        "workflowId": instance_id,
                        "query": result["query"],
                        "results": [
                            {
                                "document": r["document"],
                                "similarity": r["similarity"],
                                "interpretation": r["interpretation"]
                            }
                            for r in result["results"]
                        ],
                        "metadata": {
                            "device": result["device"],
                            "processingTimeMs": result["total_processing_time_ms"],
                            "embeddingDimension": result["embedding_dimension"],
                            "numDocuments": len(result["results"])
                        }
                    })
                else:
                    # Workflow failed or was terminated
                    yield send_sse_event("error", {
                        "message": "Workflow failed",
                        "runtimeStatus": state.runtime_status.name
                    })

            except asyncio.CancelledError:
                logger.warning(f"SSE stream cancelled for workflow {workflow_id} (client disconnected)")
                raise
            except Exception as e:
                logger.error(f"Error in SSE semantic search workflow: {e}")
                yield send_sse_event("error", {"message": str(e)})

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Encoding": "identity",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        """Global exception handler."""
        logger.error(f"Unhandled exception: {str(exc)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

    return app


if __name__ == "__main__":
    server = WebServer()
    server.run()
