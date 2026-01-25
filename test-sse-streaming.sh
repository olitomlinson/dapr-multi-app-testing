#!/bin/bash

# SSE Streaming Tests - Consolidated
# Tests all request chains to validate SSE streaming works through Dapr

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  SSE Streaming Chain Tests                                     ║"
echo "║  Testing each part of the request chain to isolate issues     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Looking for:"
echo "  ✅ Transfer-Encoding: chunked"
echo "  ❌ Content-Length: <number>"
echo ""

# Common test payload
TEST_PAYLOAD='{
  "query": "test query",
  "documents": [
    "document one",
    "document two"
  ]
}'

# Function to run a test
run_test() {
  local test_num=$1
  local title=$2
  local url=$3
  local chain=$4

  echo "=========================================="
  echo "Test $test_num: $title"
  echo "=========================================="
  echo "URL: $url"
  if [ -n "$chain" ]; then
    echo "$chain"
  fi
  echo ""

  curl -N -X POST "$url" \
    -H "Content-Type: application/json" \
    -H "Accept: text/event-stream" \
    -d "$TEST_PAYLOAD" \
    -v 2>&1 | grep -E "(HTTP|Content-Length|Transfer-Encoding|event:|data:)"

  echo ""
  echo "=========================================="
  echo ""
  sleep 1
}

# Test 1: Direct to .NET API (bypassing all Dapr)
run_test 1 \
  "Direct to .NET API (no Dapr)" \
  "http://localhost:5111/semantic-search/stream"

# Test 2: Through API's Dapr sidecar
run_test 2 \
  "Through API Dapr Sidecar" \
  "http://localhost:3500/v1.0/invoke/api/method/semantic-search/stream" \
  "This calls the API through Dapr service invocation"

# Test 5: Proxy calling API directly (bypasses Dapr service invocation)
run_test 5 \
  "Proxy -> API Direct (No Dapr)" \
  "http://localhost:8001/semantic-search/stream-direct" \
  "Chain: Client -> Proxy -> API (bypasses Dapr service invocation)"

# Test 4: Dapr-to-Dapr service invocation (bypasses proxy app)
run_test 4 \
  "Proxy Dapr -> API Dapr (bypass proxy app)" \
  "http://localhost:3502/v1.0/invoke/api/method/semantic-search/stream" \
  "Chain: Client -> Proxy-Dapr -> API-Dapr -> API"

# Test 3: Full proxy chain
run_test 3 \
  "Full Proxy Chain" \
  "http://localhost:8001/semantic-search/stream" \
  "Chain: Client -> Proxy -> Proxy-Dapr -> API-Dapr -> API"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Tests Complete                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
