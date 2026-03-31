using Dapr.Workflow;
using Microsoft.AspNetCore.Http.HttpResults;
using WorkflowConsoleApp.Activities;
using WorkflowConsoleApp.Models;

namespace WorkflowConsoleApp.Workflows
{

    public record SemanticSearchOutput2(
        string Query,
        List<DocumentScore> Results,
        string Device,
        double TotalProcessingTimeMs,
        int EmbeddingDimension,
        Approval Approval
    );

    public record Approval(
        bool Approved,
        string Approver
    );


    public class SemanticSearchWorkflow2 : Workflow<SemanticSearchInput, SemanticSearchOutput2>
    {
        public override async Task<SemanticSearchOutput2> RunAsync(
            WorkflowContext context,
            SemanticSearchInput input)
        {
            var workflowId = context.InstanceId;
            context.SetCustomStatus($"Starting semantic search for query: '{input.Query}'");

            // Step 1: Generate embedding for the query
            context.SetCustomStatus("Generating query embedding...");

            var queryEmbeddingRequest = new EmbeddingRequest(
                Texts: new List<string> { input.Query },
                Normalize: true,
                ModelName: input.ModelName,
                SandbagSeconds: input.SandbagSeconds
            );

            //await context.CreateTimer(TimeSpan.FromSeconds(5));

            var queryEmbeddingResponse = await context.CallActivityAsync<EmbeddingResponse>(
                "generate_embeddings",
                queryEmbeddingRequest,
                new WorkflowTaskOptions() { TargetAppId = "python" }
            );

            context.SetCustomStatus(
                $"Query embedding generated on {queryEmbeddingResponse.Device} " +
                $"in {queryEmbeddingResponse.ProcessingTimeMs:F2}ms"
            );

            // Step 2: Generate embeddings for all documents in batch
            context.SetCustomStatus($"Generating embeddings for {input.Documents.Count} documents...");

            var documentsEmbeddingRequest = new EmbeddingRequest(
                Texts: input.Documents,
                Normalize: true,
                ModelName: input.ModelName
            );

            var documentsEmbeddingResponse = await context.CallActivityAsync<EmbeddingResponse>(
                "generate_embeddings",
                documentsEmbeddingRequest,
                new WorkflowTaskOptions() { TargetAppId = "python" }
            );

            context.SetCustomStatus(
                $"Document embeddings generated on {documentsEmbeddingResponse.Device} " +
                $"in {documentsEmbeddingResponse.ProcessingTimeMs:F2}ms"
            );

            // Step 3: Compute similarity scores for each document
            context.SetCustomStatus("Computing similarity scores...");

            var queryEmbedding = queryEmbeddingResponse.Embeddings[0];
            var results = new List<DocumentScore>();

            for (int i = 0; i < input.Documents.Count; i++)
            {
                var docEmbedding = documentsEmbeddingResponse.Embeddings[i];

                var similarityRequest = new SimilarityRequest(
                    Embeddings1: queryEmbedding,
                    Embeddings2: docEmbedding
                );

                var similarityResponse = await context.CallActivityAsync<SimilarityResponse>(
                    "compute_similarity",
                    similarityRequest,
                    new WorkflowTaskOptions() { TargetAppId = "python" }
                );

                results.Add(new DocumentScore(
                    Document: input.Documents[i],
                    Similarity: similarityResponse.Similarity,
                    Interpretation: similarityResponse.Interpretation
                ));
            }

            // Sort by similarity (highest first)
            results = results.OrderByDescending(r => r.Similarity).ToList();

            var totalTime = queryEmbeddingResponse.ProcessingTimeMs +
                           documentsEmbeddingResponse.ProcessingTimeMs;

            context.SetCustomStatus(
                $"Semantic search complete. Best match: '{results[0].Document}' " +
                $"(similarity: {results[0].Similarity:F4})"
            );

            context.SetCustomStatus("Waiting for approval....");

            var approval = await context.WaitForExternalEventAsync<Approval>("approval_event");
            if (!approval.Approved)
                throw new Exception($"not approved, by {approval.Approver}");

            var output = new SemanticSearchOutput2(
                Query: input.Query,
                Results: results,
                Device: documentsEmbeddingResponse.Device,
                TotalProcessingTimeMs: totalTime,
                EmbeddingDimension: documentsEmbeddingResponse.Dimension,
                Approval: approval);

            context.SetCustomStatus(
                $"Semantic search complete. Best match: '{results[0].Document}' " +
                $"(similarity: {results[0].Similarity:F4})"
            );

            return output;
        }
    }
}
