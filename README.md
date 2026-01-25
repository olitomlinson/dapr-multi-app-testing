# GPU-Accelerated Semantic Search with Dapr Workflows

A demonstration of cross-language workflow orchestration using Dapr, showcasing how .NET workflows can call GPU-accelerated Python activities for semantic search.

## Key Features

- **Cross-Language Workflows**: .NET orchestrates business logic, Python handles GPU-intensive ML
- **GPU Acceleration**: Automatic device selection (MPS for Apple Silicon, CUDA for NVIDIA, CPU fallback)
- **Type-Safe Integration**: Strongly-typed data models ensure reliable communication
- **Production-Ready**: Lazy loading, batch processing, proper error handling

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

### Test the API

**Basic Request:**
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

**Real-time Streaming (SSE):**
```bash
# Direct SSE endpoint
./test-sse.sh

# Via SSE proxy (tests Dapr service invocation with streaming)
./test-sse-proxy.sh

# Browser UI
open test-sse.html
```

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
├── proxy/                       # SSE proxy service (tests Dapr streaming)
│   ├── main.py                 # FastAPI proxy with Dapr invocation
│   ├── requirements.txt
│   └── Dockerfile
├── components/                  # Dapr components
├── dapr-config/                # Dapr configuration
├── docker-compose.yml          # Docker Compose setup
├── test-sse.html               # Browser-based SSE test UI
├── test-sse.sh                 # Direct SSE test script
└── test-sse-proxy.sh           # Proxied SSE test script
```

## License

MIT License

## Contributing

Contributions welcome! Please open an issue or submit a pull request.
