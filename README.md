# Semantic Search with Dapr Workflows & SSE Streaming

A demonstration of cross-language workflow orchestration and real-time streaming using Dapr. Shows how .NET workflows can orchestrate GPU-accelerated Python activities while streaming progress updates via Server-Sent Events (SSE) through Dapr service invocation.

## Key Features

- **Cross-Language Workflows**: .NET orchestrates business logic, Python handles GPU-intensive ML
- **GPU Acceleration**: Automatic device selection (MPS for Apple Silicon, CUDA for NVIDIA, CPU fallback)
- **Type-Safe Integration**: Strongly-typed data models ensure reliable communication
- **Real-Time Streaming**: Server-Sent Events (SSE) for live workflow progress updates

## Quick Start

```bash
# Set environment variables (this is done already for you via the .env file)
export DAPR_RUNTIME_VERSION=1.17.0-rc.2
export DAPR_SCHEDULER_VERSION=1.17.0-rc.2
export DAPR_PLACEMENT_VERSION=1.17.0-rc.2

# Start all services
docker compose build
docker compose up
```

### Test the System

**Interactive Web UI (Recommended):**
```bash
# Open the web interface at http://localhost:8080
# Features:
# - Live SSE streaming with real-time updates
# - Interactive Mermaid sequence diagram showing architecture flow
# - Visual event tracking (scheduled, started, result, done)
open http://localhost:8080
```

**Basic API Request:**
```bash
curl -X POST http://localhost:5111/semantic-search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do I reset my password?",
    "documents": [
      "Steps to update your account password and recover access",
      "Installing the mobile application on your device",
      "Troubleshooting common login and authentication issues"
    ]
  }'
```

**SSE Streaming Tests:**
```bash
# Run all SSE streaming test scenarios
./test-sse-streaming.sh

# Tests include:
# 1. Direct .NET API streaming
# 2. Direct Python proxy streaming
# 3. Proxy → Dapr → .NET API (full chain)
# 4. .NET → Dapr → .NET loopback
# 5. Python → Dapr → Python loopback
```

## Architecture

The system uses a microservices architecture with Dapr for service-to-service communication:

```
Browser UI (port 8080)
    ↓
Python Proxy (port 8001)
    ↓ (Dapr Service Invoke)
Semantic Search API - .NET (port 5111)
    ↓ (Workflow)
Semantic Search Workflow - .NET
    ↓ (Activities via Dapr)
Python Activity Service (port 8000)
    → Compute Embeddings Activity (GPU)
    → Calculate Similarity Activity
```

**Key Components:**
- **Web UI**: Nginx container serving interactive test interface with live SSE updates
- **Python Proxy**: FastAPI service demonstrating SSE streaming through Dapr service invocation
- **Semantic Search API**: .NET API with workflow orchestration and SSE endpoints
- **Python Activity Service**: GPU-accelerated ML operations (sentence-transformers)
- **Dapr Sidecars**: Handle service discovery, state management, and workflow scheduling

**SSE Streaming Flow:**
1. Browser initiates POST request to `/semantic-search/stream`
2. Python proxy forwards request via Dapr service invocation
3. .NET API schedules workflow and streams events:
   - `scheduled`: Workflow queued
   - `started`: Workflow execution begun
   - `result`: Search results with similarity scores
   - `done`: Stream complete
4. All events flow back through the proxy to the browser in real-time

## Documentation

📖 **[Complete Guide: SEMANTIC_SEARCH.md](SEMANTIC_SEARCH.md)**

Comprehensive documentation including:
- API reference with examples (curl, Python, JavaScript, PowerShell)
- Architecture and component details
- Installation and GPU setup
- Performance benchmarks
- Troubleshooting guide
- Real-world use cases
- Advanced topics

## Project Structure

```
├── dotnet/                      # .NET workflow orchestration
│   ├── Workflows/
│   │   └── SemanticSearchWorkflow.cs
│   ├── Models/
│   │   └── EmbeddingModels.cs
│   └── Program.cs              # HTTP API endpoints (incl. SSE)
├── python/                      # Python GPU activities
│   ├── src/semantic_search/
│   │   ├── activities/
│   │   │   └── embedding_activity.py
│   │   └── main.py
│   └── requirements.txt
├── proxy/                       # SSE proxy service
│   ├── main.py                 # FastAPI proxy with Dapr service invocation
│   ├── requirements.txt
│   └── Dockerfile
├── web/                         # Web UI for SSE testing
│   ├── index.html              # Interactive UI with Mermaid diagram
│   ├── nginx.conf              # Nginx configuration
│   └── Dockerfile              # Nginx container
├── components/                  # Dapr components (state store, etc.)
├── dapr-config/                # Dapr configuration files
├── docker-compose.yml          # Complete service orchestration
├── test-sse.html               # Standalone SSE test UI
└── test-sse-streaming.sh       # Comprehensive SSE test suite
```

## License

MIT License

## Contributing

Contributions welcome! Please open an issue or submit a pull request.
