export type ServiceStatus = { name: string; status: 'online' | 'degraded' | 'offline'; detail: string }
export type Manifest = {
  dataset: string; dataset_source: string; dataset_mode: 'development_fixture' | 'official_subset' | 'full_dataset';
  development_fixture: boolean; official_subset?: boolean; subset_id?: string; index_id?: string;
  records: number; documents?: number; chunks: number; chunk_strategy: string; embedding_provider: string;
  embedding_mode?: string; embedding_model: string; embedding_dimension?: number; vector_store: string;
  demo_queries: string[]; created_at: string;
}
export type Health = {
  status: 'online' | 'degraded' | 'offline'; mode: 'live' | 'development_fallback';
  runtime_profile: 'local-development' | 'neural-retrieval' | 'full-production';
  services: ServiceStatus[]; dataset: string; dataset_mode: 'development_fixture' | 'official_subset' | 'full_dataset' | 'unknown';
  indexed_documents: number; indexed_chunks: number; manifest: Manifest | null;
}
export type Timing = { stage: string; duration_ms: number; status: string; attempt: number }
export type Chunk = { chunk_id: string; document_id: string; record_id: string; source: string; strategy: string; chunk_index: number; token_count: number; character_count: number; overlap: number; text: string; embedding_id: string; metadata: Record<string, unknown> }
export type Candidate = { chunk: Chunk; semantic_score: number; lexical_score: number; metadata_score: number; hybrid_score: number; rerank_score: number; rank_before: number; rank_after: number }
export type Citation = { document_id: string; chunk_id: string; quote: string }
export type Answer = { answer: string; confidence: number; grounded: boolean; citations: Citation[]; warnings: string[]; refusal: boolean; refusal_reason: string | null }
export type Analysis = { normalized_query: string; intent: string; language: string; safety_status: string; retrieval_mode: string; relevant_to_dataset: boolean }
export type ClaimSupport = { claim: string; score: number; supported: boolean; supporting_chunk_ids: string[] }
export type Grounding = { passed: boolean; score: number; supported_citations: number; total_citations: number; claims: ClaimSupport[]; reason: string }
export type ToolExecution = { tool: string; stage: string; status: string; duration_ms: number; attempt: number; error_type: string | null }
export type Trace = {
  request_id: string; timestamp: string; input_mode: 'text' | 'voice'; transcript: string | null; analysis: Analysis;
  query_plan: Record<string, unknown>; retrieval_plan: Record<string, unknown>; selected_chunk_strategy: string;
  retrieval_mode: string; candidate_count: number; top_k: number; candidates: Candidate[]; selected_evidence: Candidate[];
  context: string; model_output: Record<string, unknown>; grounding: Grounding;
  guardrail: { status: string; reason: string; flags: string[] }; timings: Timing[]; tool_calls: ToolExecution[];
  generation_attempts: number; retry_count: number; recovery_actions: string[]; cache_hit: boolean;
}
export type QueryResponse = { request_id: string; status: 'complete' | 'refused' | 'error'; answer: Answer; evidence: Candidate[]; telemetry: Timing[]; total_ms: number; trace: Trace; runtime_mode: 'live' | 'development_fallback'; dataset: string }
export type StageEvent = { request_id: string; stage: string; status: string; timestamp?: number; duration_ms?: number; transcript?: string; error?: string }
export type StreamMessage = { type: 'stage'; data: StageEvent } | { type: 'result'; data: QueryResponse } | { type: 'error'; data: { request_id?: string; timestamp?: number; code: string; message: string } }
export type Benchmark = {
  available: boolean; benchmark_id?: string; timestamp?: string;
  profile?: 'local-development' | 'neural-retrieval' | 'full-production' | 'full-voice'; query_count?: number; warmup_count?: number;
  indexed_documents?: number; indexed_chunks?: number; environment?: Record<string, unknown>;
  latency_scope?: string; cache_policy?: string; cold_cache?: boolean; p50_ms?: number; p70_ms?: number;
  p95_ms?: number; p100_ms?: number; mean_ms?: number; min_ms?: number; max_ms?: number;
  failure_rate?: number; refusal_rate?: number; grounding_pass_rate?: number; retry_rate?: number;
  avg_retrieval_ms?: number; avg_generation_ms?: number; avg_score?: number; reason?: string;
}
export type BenchmarkProfile = {
  profile: 'local-development' | 'neural-retrieval' | 'full-production' | 'full-voice';
  label: string; scope: string; available: boolean; measurement_count: number;
  latest: { benchmark_id: string; timestamp: string; p50_ms: number; p70_ms: number; p95_ms: number; p100_ms: number } | null;
}
export type MetricDetail = { name: string; queries: number; correct?: number; incorrect?: number; rate?: number | null; value?: number | null }
export type Evaluation = {
  available: boolean; evaluation_id?: string; timestamp?: string; dataset?: string; dataset_source?: string;
  dataset_mode?: string; ground_truth_source?: string; query_generation?: string; retrieval_query_count?: number;
  unique_base_queries?: number; adversarial_query_count?: number;
  retrieval_metrics?: { recall_at_1: MetricDetail; recall_at_3: MetricDetail; recall_at_5: MetricDetail; mrr: MetricDetail; ndcg_at_5: MetricDetail };
  grounding?: MetricDetail; citation_validity?: MetricDetail; answerability_accuracy?: MetricDetail;
  guardrails?: Record<string, MetricDetail>; limitations?: string[]; reason?: string;
}
export type ChunkingPreview = {
  available: boolean; generated_at?: string; source?: string; document_tokens?: number; reason?: string;
  strategies?: Record<string, { chunk_count: number; selected_algorithm: string | null; chunks: { index: number; tokens: number; overlap: number; start: string; end: string; chunk_id: string }[] }>;
}
export type PipelineStage = { id: string; name: string; what: string; why: string; implementation: string; failure_modes: string[] }
