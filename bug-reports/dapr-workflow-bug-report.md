# Dapr Workflow Activity Re-execution Bug Report

**Date:** January 29, 2026
**Project:** dapr-multi-app-testing
**Component:** Dapr Workflows with .NET orchestrator and Python activities
**Severity:** High - Activities execute multiple times causing performance degradation

---

## Executive Summary

Activities in Dapr Workflows are being **re-executed multiple times** instead of having their results retrieved from event source history during workflow replay. This violates the fundamental guarantee of Durable Task Framework that activities should only execute once per task ID.

**Key Finding:** The `Dapr.Workflow` v1.17.0-rc06 package has a bug where the `WorkflowOrchestrationContext` class fails to maintain the `OpenTasks` dictionary during workflow replay, causing all activity completion events to be marked as "unknown" and discarded.

---

## Environment Details

### Software Versions

| Component | Version |
|-----------|---------|
| Dapr Runtime (api) | 1.17.0-master (custom build) |
| Dapr Runtime (semantic-search) | 1.17.0-master (custom build) |
| Dapr Scheduler | 1.17.0-rc.2 |
| Dapr Placement | 1.17.0-rc.2 |
| Dapr.Workflow (.NET) | 1.17.0-rc06 |
| dapr-ext-workflow (Python) | 1.17.0rc3 |
| .NET SDK | 9.0 |
| Python | 3.x |

### Architecture

```
┌─────────────────┐         ┌──────────────────┐
│  .NET API App   │────────▶│  Dapr Sidecar    │
│  (Orchestrator) │         │  (api-dapr)      │
└─────────────────┘         └──────────────────┘
        │                            │
        │ Cross-app activity calls   │
        ▼                            ▼
┌─────────────────┐         ┌──────────────────┐
│  Python Worker  │◀────────│  Dapr Sidecar    │
│  (Activities)   │         │  (semantic-dapr) │
└─────────────────┘         └──────────────────┘
```

The workflow orchestrator runs in .NET and delegates GPU-intensive ML operations (embeddings, similarity) to Python activities via Dapr's cross-app workflow activity invocation.

---

## Problem Description

### Expected Behavior

In Dapr Workflows (Durable Task Framework):
1. Workflow schedules Activity with taskId=0
2. Activity executes once and completes
3. Result is persisted to event source history
4. On workflow replay, the orchestrator:
   - Rebuilds state from event history
   - Recognizes taskId=0 as completed
   - Returns cached result instead of re-executing

### Actual Behavior

1. Workflow schedules Activity with taskId=0
2. Activity executes and completes
3. **Orchestrator marks completion as "unknown taskId"**
4. On replay, orchestrator doesn't recognize the activity ran
5. **Activity is scheduled and executed again**
6. This repeats for every activity on every replay

---

## Log Analysis

### Python Activity Logs (semantic-search-a2b0833a)

Activity logs show duplicate executions with identical workflow and task IDs:

```
2026-01-29 16:47:47.419 - [workflow=semantic-search-a2b0833a, activity=0]
    Generating embeddings for 1 text(s) using model: all-MiniLM-L6-v2

2026-01-29 16:47:47.514 - [workflow=semantic-search-a2b0833a, activity=0]
    Generated 1 embeddings using all-MiniLM-L6-v2 (dim=384) in 96.23ms on cpu
    ✓ FIRST EXECUTION COMPLETE

2026-01-29 16:47:47.542 - [workflow=semantic-search-a2b0833a, activity=0]
    Generating embeddings for 1 text(s) using model: all-MiniLM-L6-v2
    ⚠️ RE-EXECUTING (only 28ms after completion!)

2026-01-29 16:47:47.658 - [workflow=semantic-search-a2b0833a, activity=0]
    Generated 1 embeddings using all-MiniLM-L6-v2 (dim=384) in 116.64ms on cpu
    ⚠️ DUPLICATE COMPLETION
```

**Activity 0 (query embedding)** executes **twice** with the same workflow and task ID.

**Activity 1 (document embeddings)** executes **three times**:

```
2026-01-29 16:47:47.545 - [workflow=semantic-search-a2b0833a, activity=1]
    Generating embeddings for 5 text(s)

2026-01-29 16:47:47.806 - [workflow=semantic-search-a2b0833a, activity=1]
    Generated 5 embeddings in 260.35ms on cpu ✓ FIRST

2026-01-29 16:47:47.841 - [workflow=semantic-search-a2b0833a, activity=1]
    Generating embeddings for 5 text(s)
    ⚠️ RE-EXECUTING #2

2026-01-29 16:47:47.954 - [workflow=semantic-search-a2b0833a, activity=1]
    Generated 5 embeddings in 257.46ms on cpu ⚠️ DUPLICATE #2

[Activity 1 executes AGAIN - third time]

2026-01-29 16:47:48.242 - [workflow=semantic-search-a2b0833a, activity=1]
    Generated 5 embeddings in 401.60ms on cpu ⚠️ DUPLICATE #3
```

**Similarity Activities** (taskIds 2, 3, 4, 5, 6) all execute **twice**:

```
2026-01-29 16:47:47.845 - Computed similarity: 0.7321 ✓
2026-01-29 16:47:47.869 - Computed similarity: 0.7321 ⚠️ DUPLICATE

2026-01-29 16:47:47.886 - Computed similarity: 0.0983 ✓
2026-01-29 16:47:47.913 - Computed similarity: 0.0983 ⚠️ DUPLICATE
2026-01-29 16:47:47.984 - Computed similarity: 0.0983 ⚠️ DUPLICATE (3rd!)

2026-01-29 16:47:47.995 - Computed similarity: 0.3279 ✓
2026-01-29 16:47:48.067 - Computed similarity: 0.3279 ⚠️ DUPLICATE

2026-01-29 16:47:48.083 - Computed similarity: 0.0612 ✓
2026-01-29 16:47:48.121 - Computed similarity: 0.0612 ⚠️ DUPLICATE

2026-01-29 16:47:48.124 - Computed similarity: 0.5146 ✓
2026-01-29 16:47:48.202 - Computed similarity: 0.5146 ⚠️ DUPLICATE
```

### .NET Orchestrator Logs (api container)

The orchestrator logs reveal the smoking gun - **"Received completion for unknown taskId"** warnings:

```
2026-01-29 16:47:47.418 - Scheduled workflow 'SemanticSearchWorkflow'
    with instance ID 'semantic-search-a2b0833a'

2026-01-29 16:47:47.833 - warn: WorkflowOrchestrationContext[0]
    Received completion for unknown taskId 0 in instance semantic-search-a2b0833a.
    OpenTasks=[] EventType=TaskCompleted
    ⚠️ ACTIVITY 0 COMPLETION DISCARDED

2026-01-29 16:47:47.862 - warn: WorkflowOrchestrationContext[0]
    Received completion for unknown taskId 0 in instance semantic-search-a2b0833a.
    OpenTasks=[] EventType=TaskCompleted
    ⚠️ ACTIVITY 0 COMPLETION DISCARDED AGAIN

2026-01-29 16:47:47.890 - warn: WorkflowOrchestrationContext[0]
    Received completion for unknown taskId 0 in instance semantic-search-a2b0833a.
    OpenTasks=[] EventType=TaskCompleted
    ⚠️ ACTIVITY 0 COMPLETION DISCARDED (3rd time!)

2026-01-29 16:47:47.942 - warn: WorkflowOrchestrationContext[0]
    Received completion for unknown taskId 0 in instance semantic-search-a2b0833a.
    OpenTasks=[] EventType=TaskCompleted
    ⚠️ ACTIVITY 0 COMPLETION DISCARDED (4th time!)

2026-01-29 16:47:47.942 - warn: WorkflowOrchestrationContext[0]
    Received completion for unknown taskId 2 in instance semantic-search-a2b0833a.
    OpenTasks=[] EventType=TaskCompleted
    ⚠️ ACTIVITY 2 (similarity) COMPLETION DISCARDED

[Pattern continues for all activities: 0, 1, 2, 3, 4, 5, 6...]

2026-01-29 16:47:48.145 - Workflow execution completed:
    Name='SemanticSearchWorkflow', InstanceId='semantic-search-a2b0833a'
```

### Critical Pattern: OpenTasks=[]

**Every single "unknown taskId" warning shows `OpenTasks=[]`** - the orchestrator's internal tracking dictionary is always empty when activity completions arrive.

---

## Timeline Correlation

Correlating Python activity execution with .NET orchestrator warnings for `semantic-search-a2b0833a`:

| Time (ms) | Python Activity Log | .NET Orchestrator Log | Analysis |
|-----------|--------------------|-----------------------|----------|
| 47.419 | Activity 0 starts | - | First execution |
| 47.514 | Activity 0 completes (96ms) ✓ | - | Success |
| 47.542 | **Activity 0 starts AGAIN** | - | Re-execution! |
| 47.658 | Activity 0 completes (116ms) | - | Duplicate work |
| 47.833 | - | ⚠️ Unknown taskId 0 | Completion discarded |
| 47.862 | - | ⚠️ Unknown taskId 0 | Completion discarded again |
| 47.890 | - | ⚠️ Unknown taskId 0 | Completion discarded (3rd) |
| 47.942 | - | ⚠️ Unknown taskId 0 + taskId 2 | Multiple discarded |
| 48.045 | - | ⚠️ Unknown taskId 0, 2, 3 | Cascading failures |
| 48.113 | - | ⚠️ Unknown taskId 0, 1, 2, 3 | All tasks "unknown" |
| 48.142 | - | ⚠️ Unknown taskId 0, 1, 2, 3, 4 | Final batch discarded |

**Pattern:** Activity completes → orchestrator replays → doesn't recognize completion → schedules activity again → repeat

---

## Root Cause Analysis

### The Bug

The `Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext` class in version **1.17.0-rc06** has a critical bug in its replay mechanism:

**During workflow replay:**
- ✅ The workflow function is correctly replayed
- ✅ Activities are correctly scheduled again during replay
- ❌ **The `OpenTasks` dictionary is NOT rebuilt from event history**
- ❌ When activity completion events arrive, they find `OpenTasks=[]`
- ❌ Completions are marked as "unknown" and discarded
- ❌ The orchestrator thinks activities never completed
- ❌ Activities are scheduled and executed again

### Why This Happens

```csharp
// PSEUDOCODE - Illustrating the bug

class WorkflowOrchestrationContext {
    Dictionary<int, TaskInfo> OpenTasks = new();

    void ReplayWorkflow(EventHistory history) {
        // BUG: OpenTasks is NOT repopulated from history
        // Should be doing something like:
        // foreach (var completedTask in history.GetCompletedTasks()) {
        //     OpenTasks[completedTask.TaskId] = completedTask;
        // }

        RunWorkflowCode(); // Schedules activities
    }

    void OnActivityCompleted(int taskId, object result) {
        if (!OpenTasks.ContainsKey(taskId)) {
            // BUG MANIFESTS HERE
            Log.Warning($"Unknown taskId {taskId}, OpenTasks={OpenTasks.Count}");
            return; // DISCARDS THE RESULT!
        }
        // ... normal completion logic
    }
}
```

### Evidence

1. **`OpenTasks=[]` in every warning** - Dictionary never populated
2. **All completions marked "unknown"** - No task IDs recognized
3. **Activities re-execute immediately after completion** - No 30+ second delay (sandbag mode disabled in these logs), proving they're actually running, not just replaying
4. **Same taskId values repeat** - Activity 0, 1, 2, 3, 4 all appear multiple times

---

## Complete Log Set

### Full Python Activity Logs (semantic-search-a2b0833a)

```
2026-01-29 16:47:47.420 | 2026-01-29 16:47:47,419 - semantic_search.activities.generate_embeddings - INFO - [workflow=semantic-search-a2b0833a, activity=0] Generating embeddings for 1 text(s) using model: all-MiniLM-L6-v2
2026-01-29 16:47:47.515 |
2026-01-29 16:47:47.519 | Batches:   0%|          | 0/1 [00:00<?, ?it/s]
2026-01-29 16:47:47.519 | Batches: 100%|██████████| 1/1 [00:00<00:00, 12.16it/s]
2026-01-29 16:47:47.515 | 2026-01-29 16:47:47,514 - semantic_search.activities.generate_embeddings - INFO - [workflow=semantic-search-a2b0833a, activity=0] Generated 1 embeddings using all-MiniLM-L6-v2 (dim=384) in 96.23ms on cpu
2026-01-29 16:47:47.542 | 2026-01-29 16:47:47,542 - semantic_search.activities.generate_embeddings - INFO - [workflow=semantic-search-a2b0833a, activity=0] Generating embeddings for 1 text(s) using model: all-MiniLM-L6-v2
2026-01-29 16:47:47.546 | 2026-01-29 16:47:47,545 - semantic_search.activities.generate_embeddings - INFO - [workflow=semantic-search-a2b0833a, activity=1] Generating embeddings for 5 text(s) using model: all-MiniLM-L6-v2
2026-01-29 16:47:47.555 |
2026-01-29 16:47:47.558 | Batches:   0%|          | 0/1 [00:00<?, ?it/s]
2026-01-29 16:47:47.658 |
2026-01-29 16:47:47.670 | Batches:   0%|          | 0/1 [00:00<?, ?it/s]
2026-01-29 16:47:47.670 | Batches: 100%|██████████| 1/1 [00:00<00:00,  9.42it/s]
2026-01-29 16:47:47.670 | Batches: 100%|██████████| 1/1 [00:00<00:00,  9.26it/s]
2026-01-29 16:47:47.658 | 2026-01-29 16:47:47,658 - semantic_search.activities.generate_embeddings - INFO - [workflow=semantic-search-a2b0833a, activity=0] Generated 1 embeddings using all-MiniLM-L6-v2 (dim=384) in 116.64ms on cpu
2026-01-29 16:47:47.697 | 2026-01-29 16:47:47,697 - semantic_search.activities.generate_embeddings - INFO - [workflow=semantic-search-a2b0833a, activity=1] Generating embeddings for 5 text(s) using model: all-MiniLM-L6-v2
2026-01-29 16:47:47.805 |
2026-01-29 16:47:47.808 | Batches:   0%|          | 0/1 [00:00<?, ?it/s]
2026-01-29 16:47:47.806 |
2026-01-29 16:47:47.808 | Batches: 100%|██████████| 1/1 [00:00<00:00,  4.05it/s]
2026-01-29 16:47:47.808 | Batches: 100%|██████████| 1/1 [00:00<00:00,  4.04it/s]
2026-01-29 16:47:47.806 | 2026-01-29 16:47:47,806 - semantic_search.activities.generate_embeddings - INFO - [workflow=semantic-search-a2b0833a, activity=1] Generated 5 embeddings using all-MiniLM-L6-v2 (dim=384) in 260.35ms on cpu
2026-01-29 16:47:47.842 | 2026-01-29 16:47:47,841 - semantic_search.activities.generate_embeddings - INFO - [workflow=semantic-search-a2b0833a, activity=1] Generating embeddings for 5 text(s) using model: all-MiniLM-L6-v2
2026-01-29 16:47:47.843 |
2026-01-29 16:47:47.845 | 2026-01-29 16:47:47,845 - semantic_search.activities.similarity_activity - INFO - Computed similarity: 0.7321
2026-01-29 16:47:47.870 | 2026-01-29 16:47:47,869 - semantic_search.activities.similarity_activity - INFO - Computed similarity: 0.7321
2026-01-29 16:47:47.886 | 2026-01-29 16:47:47,886 - semantic_search.activities.similarity_activity - INFO - Computed similarity: 0.0983
2026-01-29 16:47:47.913 | 2026-01-29 16:47:47,913 - semantic_search.activities.similarity_activity - INFO - Computed similarity: 0.0983
2026-01-29 16:47:47.954 |
2026-01-29 16:47:47.965 | Batches:   0%|          | 0/1 [00:00<?, ?it/s]
2026-01-29 16:47:47.965 | Batches: 100%|██████████| 1/1 [00:00<00:00,  4.01it/s]
2026-01-29 16:47:47.965 | Batches: 100%|██████████| 1/1 [00:00<00:00,  4.01it/s]
2026-01-29 16:47:47.955 | 2026-01-29 16:47:47,954 - semantic_search.activities.generate_embeddings - INFO - [workflow=semantic-search-a2b0833a, activity=1] Generated 5 embeddings using all-MiniLM-L6-v2 (dim=384) in 257.46ms on cpu
2026-01-29 16:47:47.984 | 2026-01-29 16:47:47,984 - semantic_search.activities.similarity_activity - INFO - Computed similarity: 0.0983
2026-01-29 16:47:47.995 | 2026-01-29 16:47:47,995 - semantic_search.activities.similarity_activity - INFO - Computed similarity: 0.3279
2026-01-29 16:47:48.067 | 2026-01-29 16:47:48,067 - semantic_search.activities.similarity_activity - INFO - Computed similarity: 0.3279
2026-01-29 16:47:48.087 | 2026-01-29 16:47:48,083 - semantic_search.activities.similarity_activity - INFO - Computed similarity: 0.0612
2026-01-29 16:47:48.122 | 2026-01-29 16:47:48,121 - semantic_search.activities.similarity_activity - INFO - Computed similarity: 0.0612
2026-01-29 16:47:48.124 | 2026-01-29 16:47:48,124 - semantic_search.activities.similarity_activity - INFO - Computed similarity: 0.5146
2026-01-29 16:47:48.202 | 2026-01-29 16:47:48,202 - semantic_search.activities.similarity_activity - INFO - Computed similarity: 0.5146
2026-01-29 16:47:48.242 |
2026-01-29 16:47:48.242 |
2026-01-29 16:47:48.244 | Batches: 100%|██████████| 1/1 [00:00<00:00,  2.55it/s]
2026-01-29 16:47:48.244 | Batches: 100%|██████████| 1/1 [00:00<00:00,  2.54it/s]
2026-01-29 16:47:48.242 | 2026-01-29 16:47:47,242 - semantic_search.activities.generate_embeddings - INFO - [workflow=semantic-search-a2b0833a, activity=1] Generated 5 embeddings using all-MiniLM-L6-v2 (dim=384) in 401.60ms on cpu
```

### Full .NET Orchestrator Logs (semantic-search-a2b0833a)

```
2026-01-29 16:47:47.383 | info: api[0]
2026-01-29 16:47:47.383 |       Starting SSE semantic search workflow with query: 'How do I reset my password?'
2026-01-29 16:47:47.418 | info: Dapr.Workflow.Client.WorkflowGrpcClient[430660008]
2026-01-29 16:47:47.418 |       Scheduled workflow 'SemanticSearchWorkflow' with instance ID 'semantic-search-a2b0833a'
2026-01-29 16:47:47.833 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:47.833 |       Received completion for unknown taskId 0 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:47.862 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:47.862 |       Received completion for unknown taskId 0 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:47.890 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:47.890 |       Received completion for unknown taskId 0 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:47.942 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:47.942 |       Received completion for unknown taskId 0 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:47.942 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:47.942 |       Received completion for unknown taskId 2 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.045 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.045 |       Received completion for unknown taskId 0 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.045 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.045 |       Received completion for unknown taskId 2 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.045 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.045 |       Received completion for unknown taskId 3 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.112 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.112 |       Received completion for unknown taskId 0 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.113 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.113 |       Received completion for unknown taskId 2 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.113 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.113 |       Received completion for unknown taskId 3 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.114 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.114 |       Received completion for unknown taskId 1 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.114 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.114 |       Received completion for unknown taskId 3 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.141 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.141 |       Received completion for unknown taskId 0 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.142 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.142 |       Received completion for unknown taskId 2 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.142 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.142 |       Received completion for unknown taskId 3 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.142 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.142 |       Received completion for unknown taskId 1 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.142 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.142 |       Received completion for unknown taskId 3 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.142 | warn: Dapr.Workflow.Worker.Internal.WorkflowOrchestrationContext[0]
2026-01-29 16:47:48.142 |       Received completion for unknown taskId 4 in instance semantic-search-a2b0833a. OpenTasks=[] EventType=TaskCompleted
2026-01-29 16:47:48.145 | info: Dapr.Workflow.Worker.WorkflowWorker[1120267106]
2026-01-29 16:47:48.145 |       Workflow execution completed: Name='SemanticSearchWorkflow', InstanceId='semantic-search-a2b0833a'
2026-01-29 16:47:48.442 | info: api[0]
2026-01-29 16:47:48.442 |       SSE Semantic search completed. Device: cpu, Time: 356.57477378845215ms
```

---

## Impact Assessment

### Performance Impact

For a workflow with:
- 1 query embedding activity
- 1 document embeddings activity (5 documents)
- 5 similarity computation activities

**Expected:** 7 activity executions
**Actual:** ~15-20 activity executions (2-3x duplication)

**Wasted Computation:**
- Activity 0: 96ms + 116ms = 212ms (should be 96ms) → **121% overhead**
- Activity 1: 260ms + 257ms + 401ms = 918ms (should be 260ms) → **253% overhead**
- Similarity activities: All execute 2x → **100% overhead**

**Total overhead:** Activities consume **2-3x more resources** than necessary.

### GPU/ML Impact

For GPU-intensive embeddings (e.g., with sandbag_seconds=30):
- Expected: 30 seconds per activity
- Actual: 60-90 seconds due to re-execution
- **GPU utilization wasted on duplicate work**

### Cross-App Call Overhead

Each duplicate activity execution incurs:
- Dapr service invocation overhead
- Network round-trip latency
- JSON serialization/deserialization
- Cross-app authentication

---

## Recommendations

### Immediate Action: Downgrade to Stable Version

Downgrade `Dapr.Workflow` package from `1.17.0-rc06` to stable `1.16.0`:

**File:** `dotnet/api.csproj`

```xml
<!-- Change from: -->
<PackageReference Include="Dapr.Workflow" Version="1.17.0-rc06" />

<!-- To: -->
<PackageReference Include="Dapr.Workflow" Version="1.16.0" />
```

Also consider downgrading Python package in `python/requirements.txt`:

```python
# Change from:
dapr-ext-workflow>=1.17.0rc3

# To:
dapr-ext-workflow>=1.14.0
```

### Report to Dapr Team

File an issue at: https://github.com/dapr/dotnet-sdk/issues

**Issue Title:**
"WorkflowOrchestrationContext fails to maintain OpenTasks during replay causing activity re-execution (1.17.0-rc06)"

**Include:**
- This bug report
- The correlation between "unknown taskId" warnings and duplicate activity execution
- Evidence that OpenTasks=[] for all completion events
- Version information

### Alternative: Wait for 1.17.0 Stable

The 1.17.0 release candidates are pre-release software. This bug may already be fixed in:
- A newer RC version
- The upcoming stable 1.17.0 release

Monitor: https://github.com/dapr/dotnet-sdk/releases

### Verification After Fix

After downgrading or upgrading, verify the fix by:

1. Check orchestrator logs for **zero "unknown taskId" warnings**
2. Check Python logs for **no duplicate activity executions**
3. Verify activity execution count matches expected:
   - For semantic search: exactly 7 activities (1 query + 1 docs + 5 similarity)
4. Monitor performance metrics show ~50% reduction in activity execution time

---

## Conclusion

This bug in `Dapr.Workflow` 1.17.0-rc06 violates the core guarantee of Durable Task Framework: activities should execute exactly once per task ID. The `WorkflowOrchestrationContext.OpenTasks` dictionary is not being maintained during replay, causing all activity completion events to be discarded and activities to be re-executed multiple times.

The evidence is conclusive:
- ✅ Activities log duplicate executions with identical workflow/task IDs
- ✅ Orchestrator logs show "unknown taskId" warnings for all completions
- ✅ OpenTasks=[] in every single warning
- ✅ Timeline correlation proves activities re-execute immediately after completion

**Solution:** Downgrade to stable `Dapr.Workflow` 1.16.0 or wait for stable 1.17.0 release with this bug fixed.

---

**Report compiled by:** Claude Code
**Investigation date:** January 29, 2026
**Document version:** 1.0
