// codecontext-rag/frontend/src/types/api.types.ts

// Core Types
export type Reason = { 
  type: string; 
  score: number; 
  explanation: string 
}

export type Chunk = { 
  file_path: string
  start_line: number
  end_line: number
  language: string
  snippet: string
  confidence: number
  reasons: Reason[]
  distance?: number 
}

export type Artifact = { 
  type: string
  label: string
  content: string 
}

export type JobStatus = { 
  job_id: string
  status: "queued" | "running" | "completed" | "failed"
  progress?: { 
    current: number
    total: number
    percentage: number 
  }
  started_at?: string
  completed_at?: string
  error?: string | null 
}

export type Repo = { 
  id: string
  owner: string
  name: string
  full_name: string
  branch: string
  status: string
  indexed_at?: string | null
  statistics?: {
    total_files: number
    indexed_files: number
  }
}

export type Recommendation = { 
  file_path: string
  confidence: number
  reasons: Reason[]
  metadata?: { 
    language?: string
    lines_of_code?: number 
  } 
}

export type ExecutionResult = { 
  success: boolean
  exit_code?: number
  stdout?: string
  stderr?: string
  tests_run?: number
  tests_passed?: number
  tests_failed?: number
  runtime_seconds?: number 
}

// Repository Types
export interface Repository {
  id: string
  owner: string
  name: string
  full_name: string
  branch: string
  status: 'pending' | 'indexing' | 'indexed' | 'error'
  indexed_at?: string
  created_at?: string
  statistics?: {
    total_files: number
    indexed_files: number
  }
}

// Feature & Product Types
export interface Feature {
  id: string
  repo_id: string
  name: string
  description: string
  category: string
  code_files: string[]
  api_endpoints: string[]
  ui_components: string[]
  maturity: string
  confidence: number
  created_at: string
}

export interface FeatureSuggestion {
  id: string
  repo_id: string
  title: string
  description: string
  rationale: string
  market_evidence: any
  priority: 'critical' | 'high' | 'medium' | 'low'
  effort_estimate: 'small' | 'medium' | 'large' | 'xl'
  dependencies: string[]
  status: 'proposed' | 'approved' | 'in_progress' | 'completed' | 'rejected'
  proposed_by: string
  created_at: string
}

export interface ConversationMessage {
  id: string
  agent_role: string
  message: string
  reasoning: string
  metadata?: any
  created_at: string
}

export interface AgentAnalysis {
  id: string
  agent_role: string
  analysis_type: string
  summary: string
  details: any
  created_at: string
}

// Context & Retrieval Types
export interface ContextChunk {
  file_path: string
  start_line: number
  end_line: number
  language: string
  snippet: string
  confidence: number
  reasons: Reason[]
  distance?: number
}

export interface ContextResponse {
  query: string
  chunks: ContextChunk[]
  summary?: { 
    total_chunks: number
    avg_confidence: number
    retrieval_mode: string 
  }
  artifacts?: Artifact[]
}

// Graph Types
export interface GraphNode {
  id: string
  label: string
  type: string
}

export interface GraphEdge {
  source: string
  target: string
  type: string
  weight?: number
}

export interface Graph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

// Patch Types
export interface PatchValidation {
  ok: boolean
  issues: string[]
  files: string[]
}

export interface Patch {
  model?: string
  messages_used: number
  patch: string
  validation: PatchValidation
  dry_run: boolean
}

// File Recommendation Types
export interface FileRecommendation {
  file_path: string
  confidence: number
  reasons: Reason[]
  metadata?: any
}

// Search Types
export interface SearchResult {
  file_path: string
  entity_type: string
  entity_name?: string
  similarity_score: number
  code_snippet: string
  line_number: number
  metadata?: {
    language?: string
    entity_id?: string
    repo_id?: string
  }
}

// Entity & Metadata Types
export interface EntityMetadata {
  entity_id: string
  name: string
  entity_type: string
  file_path: string
  start_line: number
  end_line: number
  code?: string
  language: string
  metrics?: {
    lines_of_code: number
    centrality: number
    recency_score: number
    change_frequency: number
  }
  git_context?: {
    recency_score: number
    change_frequency: number
    is_hotspot: boolean
  }
}

export interface FileMetadata {
  file_path: string
  language: string
  entities_count: number
  functions_list: string[]
  classes_list: string[]
  metrics?: {
    lines_of_code: number
    centrality: number
    recency_score: number
    change_frequency: number
  }
}

export interface SymbolDefinition {
  entity_id: string
  name: string
  entity_type: string
  file_path: string
  start_line: number
  end_line: number
  code: string
  language: string
}

export interface SymbolUsage {
  file_path: string
  start_line: number
  end_line: number
  lines_with_symbol: string[]
  context?: string
}

// Impact Analysis Types
export interface ImpactAnalysis {
  modified_files: string[]
  impact: {
    risk_level: 'low' | 'medium' | 'high'
    affected_files: Array<{
      file_path: string
      impact_type: 'direct' | 'historical'
      distance: number
      confidence: number
    }>
    test_files: string[]
    recommendations: string[]
    statistics: {
      total_affected: number
      direct_dependencies: number
      transitive_dependencies: number
    }
  }
}

// Task Analysis Types
export interface TaskAnalysis {
  task_type: string
  complexity: 'simple' | 'moderate' | 'complex'
  impact: 'low' | 'medium' | 'high'
  files_to_modify: string[]
  estimated_file_count: number
  is_breaking_change: boolean
  needs_database_migration: boolean
  dependencies: string[]
  test_strategy?: string
  existing_tests_affected: string[]
  summary: string
  rationale: string
  risks: string[]
  confidence_score: number
  llm_model_used?: string
  analysis_timestamp?: string
}

export interface StrategyDecision {
  strategy: 'direct' | 'branch'
  confidence: number
  primary_reason: string
  contributing_factors: string[]
  rules_applied: string[]
  rules_considered: number
  estimated_risk_level: string
  risk_factors: string[]
  alternative_strategy?: string
  alternative_reasoning?: string
  explanation: string
  recommendation: string
}

export interface StrategyRule {
  name: string
  condition: string
  suggested_strategy: 'direct' | 'branch'
  priority: number
  reasoning: string
}

// Orchestration Types
export interface OrchestrateStep {
  step_id: string
  type: 'branch_create' | 'patch_apply' | 'validate' | 'branch_merge'
  status: 'pending' | 'running' | 'success' | 'failed'
  params?: any
  result?: any
  error?: string
  timestamp: string
}

export interface OrchestrateExecution {
  execution_id: string
  status: 'running' | 'completed' | 'failed'
  task_analysis?: TaskAnalysis
  strategy?: StrategyDecision
  steps: OrchestrateStep[]
  final_result?: any
  started_at: string
  completed_at?: string
}

// Agent Feedback Types
export interface FeedbackSummary {
  avg_retrieval_precision?: number
  execution_success_rate?: number
  avg_blast_radius_accuracy?: number
  change_success_rate?: number
}

export interface RetrievalProfile {
  weights?: Record<string, number>
  hybrid_alpha?: number
  agentic_expansion_enabled?: boolean
  agentic_neighbor_enabled?: boolean
  last_updated?: string
}

// Runner Validation Types
export interface ValidationRun {
  run_id: string
  completed: boolean
  status: 'started' | 'running' | 'completed' | 'failed'
  result?: any
  attempts?: number
  execution_enabled?: boolean
  execution_result?: ExecutionResult
}

// Health & Metrics Types
export interface HealthStatus {
  status: string
  version?: string
  uptime?: number
  dependencies?: Record<string, string>
}

export interface SearchHealthStatus {
  status: string
  service: string
  vector_store: string
  embedder: string
  search_types: string[]
}

// API Response wrapper
export interface ApiResponse<T> {
  success: boolean
  data: T
  error?: {
    code: string
    message: string
    details?: any
  }
  metadata: {
    timestamp: string
    request_id: string
    version: string
  }
}

// API Error
export interface ApiError {
  status?: number
  code: string
  message: string
  requestId?: string
}

// Prompt Types
export interface PromptMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
  meta?: any
}

export interface PromptResponse {
  query: string
  model?: string
  messages: PromptMessage[]
  selected_chunks: Array<{
    id: string
    file_path: string
    start_line: number
    end_line: number
    language: string
    confidence: number
    reasons?: Reason[]
  }>
  token_usage: {
    budget: number
    estimated_tokens: number
    temperature?: number
    model?: string
    chunks_included: number
  }
  summary?: any
  artifacts?: Artifact[]
}

// Test Types
export interface TestCoverage {
  test_files: string[]
  framework?: string
  run_command?: string
}

export interface RankedTest {
  test: string
  score: number
}

export interface TestRunResult {
  ok: boolean
  output: string
}