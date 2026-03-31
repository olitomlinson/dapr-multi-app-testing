using Dapr.Workflow;
using WorkflowConsoleApp.Models;

namespace WorkflowConsoleApp.Activities
{
    /// <summary>
    /// Stub activity for generating text embeddings.
    /// Returns static stub data instead of actually computing embeddings.
    /// </summary>
    public class GenerateEmbeddingsActivity : WorkflowActivity<EmbeddingRequest, EmbeddingResponse>
    {
        private readonly ILogger<GenerateEmbeddingsActivity> _logger;

        public GenerateEmbeddingsActivity(ILogger<GenerateEmbeddingsActivity> logger)
        {
            _logger = logger;
        }

        public override Task<EmbeddingResponse> RunAsync(WorkflowActivityContext context, EmbeddingRequest input)
        {
            var workflowId = context.InstanceId;
            _logger.LogInformation(
                "[workflow={WorkflowId}] Generating stub embeddings for {Count} text(s)",
                workflowId,
                input.Texts.Count
            );

            // Simulate delay if sandbag_seconds is set
            if (input.SandbagSeconds.HasValue && input.SandbagSeconds.Value > 0)
            {
                _logger.LogWarning(
                    "[workflow={WorkflowId}] Sandbag mode: Sleeping for {Seconds} seconds",
                    workflowId,
                    input.SandbagSeconds.Value
                );
                Thread.Sleep(input.SandbagSeconds.Value * 1000);
            }

            // Generate stub embeddings (384-dimensional vectors with random-looking but consistent values)
            var embeddings = new List<List<double>>();
            var random = new Random(42); // Fixed seed for consistent results

            for (int i = 0; i < input.Texts.Count; i++)
            {
                var embedding = new List<double>();
                for (int j = 0; j < 384; j++)
                {
                    // Generate deterministic "random" values between -1 and 1
                    embedding.Add((random.NextDouble() * 2) - 1);
                }
                embeddings.Add(embedding);
            }

            var response = new EmbeddingResponse(
                Embeddings: embeddings,
                ModelName: input.ModelName ?? "stub-model-dotnet",
                Device: "cpu (stub)",
                Dimension: 384,
                ProcessingTimeMs: 10.5,
                NumTexts: input.Texts.Count
            );

            _logger.LogInformation(
                "[workflow={WorkflowId}] Generated {Count} stub embeddings (dim={Dimension})",
                workflowId,
                embeddings.Count,
                response.Dimension
            );

            return Task.FromResult(response);
        }
    }
}
