using Dapr.Workflow;
using Dapr.Client;
using WorkflowConsoleApp.Workflows;
using WorkflowConsoleApp.Models;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddHttpClient();
builder.Services.AddDaprClient();
builder.Services.AddDaprWorkflow(options =>
{
    options.RegisterWorkflow<SemanticSearchWorkflow>();
});

builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy.AllowAnyOrigin()
              .AllowAnyMethod()
              .AllowAnyHeader();
    });
});

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

app.UseCors();

app.MapSubscribeHandler();

app.Logger.LogInformation("DAPR_HTTP_PORT: " + Environment.GetEnvironmentVariable("DAPR_HTTP_PORT"));
app.Logger.LogInformation("DAPR_GRPC_PORT: " + Environment.GetEnvironmentVariable("DAPR_GRPC_PORT"));

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.MapPost("/semantic-search/stream", async (HttpContext context, DaprWorkflowClient workflowClient, SemanticSearchRequest request) =>
{
    string workflowId = $"semantic-search-{Guid.NewGuid().ToString()[..8]}";

    // Declare these outside try block so they're accessible in finally
    CancellationTokenSource? linkedCts = null;
    Task? heartbeatTask = null;

    try
    {
        app.Logger.LogInformation("Starting SSE semantic search workflow with query: '{Query}'", request.Query);

        // Set SSE headers
        context.Response.Headers["Content-Type"] = "text/event-stream";
        context.Response.Headers["Cache-Control"] = "no-cache";
        context.Response.Headers["Connection"] = "keep-alive";
        context.Response.Headers["Content-Encoding"] = "identity";  // Prevent compression by proxies

        // CRITICAL: Disable buffering and force chunked transfer encoding for streaming
        // Without this, ASP.NET will set Content-Length which breaks streaming
        context.Response.Headers.Remove("Content-Length");
        context.Features.Get<Microsoft.AspNetCore.Http.Features.IHttpResponseBodyFeature>()?.DisableBuffering();

        // Start the response to commit headers and prevent Content-Length calculation
        await context.Response.StartAsync();

        // Create linked cancellation token that triggers on either client disconnect or manual cancellation
        linkedCts = CancellationTokenSource.CreateLinkedTokenSource(context.RequestAborted);
        var cancellationToken = linkedCts.Token;

        // Start background task to send heartbeats immediately
        heartbeatTask = SendHeartbeatsAsync(context.Response, app.Logger, workflowId, cancellationToken);

        var input = new SemanticSearchInput(
            Query: request.Query,
            Documents: request.Documents,
            ModelName: request.ModelName,
            SandbagSeconds: request.SandbagSeconds
        );

        // Start the workflow
        var instanceId = await workflowClient.ScheduleNewWorkflowAsync(
        name: nameof(SemanticSearchWorkflow),
        instanceId: workflowId,
        input: input);

        // Send scheduled event
        await WriteSSEAsync(context.Response, "scheduled", new
        {
            workflowId = instanceId,
            query = request.Query,
            numDocuments = request.Documents.Count,
            modelName = request.ModelName
        });

        // Wait for workflow to actually start
        await workflowClient.WaitForWorkflowStartAsync(
            instanceId,
            getInputsAndOutputs: true,
            cancellationToken);

        // Send started event
        await WriteSSEAsync(context.Response, "started", new
        {
            workflowId = instanceId
        });

        // Wait for workflow to complete or client to disconnect
        var state = await workflowClient.WaitForWorkflowCompletionAsync(
            instanceId,
            getInputsAndOutputs: true,
            cancellationToken
        );

        // Check if workflow completed successfully
        if (state.RuntimeStatus == WorkflowRuntimeStatus.Completed)
        {
            var result = state.ReadOutputAs<SemanticSearchOutput>();

            if (result != null)
            {
                app.Logger.LogInformation(
                    "SSE Semantic search completed. Device: {Device}, Time: {Time}ms",
                    result.Device,
                    result.TotalProcessingTimeMs
                );

                // Send final result
                await WriteSSEAsync(context.Response, "result", new
                {
                    workflowId = instanceId,
                    query = result.Query,
                    results = result.Results.Select(r => new
                    {
                        document = r.Document,
                        similarity = r.Similarity,
                        interpretation = r.Interpretation
                    }),
                    metadata = new
                    {
                        device = result.Device,
                        processingTimeMs = result.TotalProcessingTimeMs,
                        embeddingDimension = result.EmbeddingDimension,
                        numDocuments = result.Results.Count
                    }
                });
            }
            else
            {
                await WriteSSEAsync(context.Response, "error", new { message = "Workflow completed but no output" });
            }
        }
        else
        {
            // Workflow failed or was terminated
            await WriteSSEAsync(context.Response, "error", new
            {
                message = "Workflow failed",
                runtimeStatus = state.RuntimeStatus.ToString()
            });
        }
    }
    catch (OperationCanceledException)
    {
        // Client disconnected or request was cancelled
        app.Logger.LogWarning("SSE stream cancelled for workflow {WorkflowId} (client disconnected)", workflowId);
        // Don't try to write to response - connection is already closed
    }
    catch (Exception ex)
    {
        app.Logger.LogError(ex, "Error in SSE semantic search workflow");
        try
        {
            await WriteSSEAsync(context.Response, "error", new { message = ex.Message });
        }
        catch
        {
            // Response stream may be closed, ignore write errors
        }
    }
    finally
    {
        // Guarantee heartbeat task cleanup regardless of how the try block exits
        if (linkedCts != null && heartbeatTask != null)
        {
            try
            {
                linkedCts.Cancel();
                await heartbeatTask;
                linkedCts.Dispose();
            }
            catch (Exception ex)
            {
                app.Logger.LogWarning(ex, "Error cleaning up heartbeat task for workflow {WorkflowId}", workflowId);
            }
        }
    }

    return Results.Empty;
}).Produces(200, contentType: "text/event-stream")
  .ProducesValidationProblem()
  .WithName("SemanticSearchStream")
  .WithTags("GPU-Accelerated Workflows");

app.MapPost("/semantic-search", async (DaprWorkflowClient workflowClient, SemanticSearchRequest request) =>
{
    try
    {
        string workflowId = $"semantic-search-{Guid.NewGuid().ToString()[..8]}";

        app.Logger.LogInformation("Starting semantic search workflow with query: '{Query}'", request.Query);

        var input = new SemanticSearchInput(
            Query: request.Query,
            Documents: request.Documents,
            ModelName: request.ModelName,
            SandbagSeconds: request.SandbagSeconds
        );

        // Start the workflow
        var instanceId = await workflowClient.ScheduleNewWorkflowAsync(
            name: nameof(SemanticSearchWorkflow),
            instanceId: workflowId,
            input: input
        );

        // Wait for the workflow to complete
        var workflowState = await workflowClient.WaitForWorkflowCompletionAsync(
            instanceId: instanceId,
            getInputsAndOutputs: true
        );

        var result = workflowState.ReadOutputAs<SemanticSearchOutput>()
            ?? throw new Exception("Workflow completed but returned no output");

        app.Logger.LogInformation(
            "Semantic search completed. Device: {Device}, Time: {Time}ms",
            result.Device,
            result.TotalProcessingTimeMs
        );

        return Results.Ok(new
        {
            workflowId = instanceId,
            query = result.Query,
            results = result.Results.Select(r => new
            {
                document = r.Document,
                similarity = r.Similarity,
                interpretation = r.Interpretation
            }),
            metadata = new
            {
                device = result.Device,
                processingTimeMs = result.TotalProcessingTimeMs,
                embeddingDimension = result.EmbeddingDimension,
                numDocuments = result.Results.Count
            }
        });
    }
    catch (TimeoutException)
    {
        app.Logger.LogError("Semantic search workflow timed out");
        return Results.StatusCode(504);
    }
    catch (Exception ex)
    {
        app.Logger.LogError(ex, "Error executing semantic search workflow");
        return Results.Problem(
            detail: ex.Message,
            statusCode: 500,
            title: "Semantic search failed"
        );
    }
}).Produces<object>()
  .ProducesValidationProblem()
  .WithName("SemanticSearch")
  .WithTags("GPU-Accelerated Workflows");

app.MapGet("/semantic-search/workflow/{workflowId}", async (string workflowId, DaprWorkflowClient workflowClient) =>
{
    try
    {
        app.Logger.LogInformation("Retrieving workflow results for: {WorkflowId}", workflowId);

        var state = await workflowClient.GetWorkflowStateAsync(
            instanceId: workflowId,
            getInputsAndOutputs: true
        );

        if (state == null)
        {
            app.Logger.LogWarning("Workflow not found: {WorkflowId}", workflowId);
            return Results.NotFound(new { message = $"Workflow '{workflowId}' not found" });
        }

        var response = new
        {
            workflowId,
            status = state.RuntimeStatus.ToString(),
            input = state.ReadInputAs<SemanticSearchInput>(),
            output = state.RuntimeStatus == WorkflowRuntimeStatus.Completed
                ? state.ReadOutputAs<SemanticSearchOutput>()
                : null
        };

        app.Logger.LogInformation(
            "Retrieved workflow: {WorkflowId}, Status: {Status}",
            workflowId,
            state.RuntimeStatus
        );

        return Results.Ok(response);
    }
    catch (Exception ex)
    {
        app.Logger.LogError(ex, "Error retrieving workflow results for: {WorkflowId}", workflowId);
        return Results.Problem(
            detail: ex.Message,
            statusCode: 500,
            title: "Failed to retrieve workflow"
        );
    }
}).Produces<object>()
  .Produces(404)
  .WithName("GetWorkflowResults")
  .WithTags("GPU-Accelerated Workflows");

app.Run();

static async Task SendHeartbeatsAsync(HttpResponse response, ILogger logger, string workflowId, CancellationToken cancellationToken)
{
    var heartbeatInterval = TimeSpan.FromSeconds(15);
    try
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            await Task.Delay(heartbeatInterval, cancellationToken);
            if (!cancellationToken.IsCancellationRequested)
            {
                try
                {
                    await WriteSSEAsync(response, "heartbeat", new { timestamp = DateTime.UtcNow });
                    logger.LogDebug("Sent SSE heartbeat for workflow {WorkflowId}", workflowId);
                }
                catch (Exception ex)
                {
                    // Connection lost - log and exit heartbeat loop
                    logger.LogWarning(ex, "Failed to send heartbeat for workflow {WorkflowId} - connection likely closed", workflowId);
                    break;
                }
            }
        }
    }
    catch (OperationCanceledException)
    {
        // Expected when workflow completes or client disconnects
    }
}

static async Task WriteSSEAsync(HttpResponse response, string eventType, object data)
{
    var json = System.Text.Json.JsonSerializer.Serialize(data);
    await response.WriteAsync($"event: {eventType}\n");
    await response.WriteAsync($"data: {json}\n\n");
    await response.Body.FlushAsync();
}

public record SemanticSearchRequest(
    [property: System.Text.Json.Serialization.JsonPropertyName("query")] string Query,
    [property: System.Text.Json.Serialization.JsonPropertyName("documents")] List<string> Documents,
    [property: System.Text.Json.Serialization.JsonPropertyName("model_name")] string? ModelName = null,
    [property: System.Text.Json.Serialization.JsonPropertyName("sandbag_seconds")] int? SandbagSeconds = null
);
