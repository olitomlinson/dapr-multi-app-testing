using Dapr.Workflow;
using WorkflowConsoleApp.Models;

namespace WorkflowConsoleApp.Activities
{
    /// <summary>
    /// Stub activity for computing cosine similarity between embeddings.
    /// Returns static stub data instead of actually computing similarity.
    /// </summary>
    public class ComputeSimilarityActivity : WorkflowActivity<SimilarityRequest, SimilarityResponse>
    {
        private readonly ILogger<ComputeSimilarityActivity> _logger;

        public ComputeSimilarityActivity(ILogger<ComputeSimilarityActivity> logger)
        {
            _logger = logger;
        }

        public override Task<SimilarityResponse> RunAsync(WorkflowActivityContext context, SimilarityRequest input)
        {
            var workflowId = context.InstanceId;
            _logger.LogInformation(
                "[workflow={WorkflowId}] Computing stub similarity between two embeddings",
                workflowId
            );

            // Return stub similarity score (could compute real cosine similarity if desired)
            // For now, return a deterministic value based on embedding dimensions
            double similarity = 0.75 + (new Random(input.Embeddings1.Count).NextDouble() * 0.2);

            var interpretation = InterpretSimilarity(similarity);

            _logger.LogInformation(
                "[workflow={WorkflowId}] Computed stub similarity: {Similarity:F4} ({Interpretation})",
                workflowId,
                similarity,
                interpretation
            );

            var response = new SimilarityResponse(
                Similarity: similarity,
                Interpretation: interpretation
            );

            return Task.FromResult(response);
        }

        private static string InterpretSimilarity(double score)
        {
            return score switch
            {
                >= 0.9 => "very_similar",
                >= 0.7 => "similar",
                >= 0.5 => "somewhat_similar",
                >= 0.3 => "slightly_similar",
                _ => "dissimilar"
            };
        }
    }
}
