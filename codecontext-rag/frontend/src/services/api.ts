// codecontext-rag/frontend/src/services/api.ts
import axios, { AxiosInstance, AxiosRequestConfig } from 'axios'

// Helper to get API key from localStorage
const getToken = () => localStorage.getItem('api_key')

class ApiService {
  private client: AxiosInstance

  constructor() {
    const baseURL = import.meta.env.VITE_API_BASE || 'http://192.168.0.9:7998'
    this.client = axios.create({
      baseURL,
      headers: { 'Content-Type': 'application/json' }
    })

    // Add auth interceptor
    this.client.interceptors.request.use((config) => {
      const token = getToken()
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    })

    // Add response interceptor for 401 handling
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        if (error.response?.status === 401) {
          const apiKey = prompt('Please enter your API key:')
          if (apiKey) {
            localStorage.setItem('api_key', apiKey)
            error.config.headers.Authorization = `Bearer ${apiKey}`
            return this.client.request(error.config)
          }
        }
        throw error
      }
    )
  }

  private async request<T>(
    method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
    url: string,
    options: { data?: any; params?: any } = {}
  ): Promise<T> {
    try {
      const config: AxiosRequestConfig = {
        method,
        url,
        params: options.params,
        data: options.data
      }
      const response = await this.client.request(config)
      const body = response.data

      // Handle both envelope and raw responses
      if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
        return body.data as T
      }
      return body as T
    } catch (error: any) {
      const requestId = error.response?.headers?.['x-request-id'] || 
                      error.response?.data?.metadata?.request_id
      const message = error.response?.data?.error?.message || 
                    error.response?.data?.message || 
                    error.message
      const code = error.response?.data?.error?.code || String(error.response?.status || 'UNKNOWN')
      
      throw {
        status: error.response?.status,
        code,
        message,
        requestId  // Now it's used in the throw
      }
    }
  }

  // Streaming helper for patches
  async streamPatch(
    repoId: string,
    data: any,
    onChunk: (chunk: string) => void,
    signal?: AbortSignal
  ): Promise<void> {
    const response = await fetch(`${this.client.defaults.baseURL}/repositories/${repoId}/patch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {})
      },
      body: JSON.stringify({ ...data, stream: true }),
      signal
    })

    if (!response.ok) throw new Error(`Stream failed: ${response.statusText}`)
    
    const reader = response.body?.getReader()
    const decoder = new TextDecoder()
    
    if (!reader) throw new Error('No reader available')
    
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      onChunk(decoder.decode(value, { stream: true }))
    }
  }

  // Polling helper
  async poll<T>(
    url: string,
    stopWhen: (data: T) => boolean,
    intervalMs = 1500,
    maxAttempts = 60
  ): Promise<T> {
    let attempts = 0
    while (attempts < maxAttempts) {
      const data = await this.request<T>('GET', url)
      if (stopWhen(data)) return data
      await new Promise(resolve => setTimeout(resolve, intervalMs))
      attempts++
    }
    throw new Error('Polling timeout')
  }

  // Health & Metrics
  async health() {
    return this.request<any>('GET', '/health')
  }

  async metrics() {
    return this.request<any>('GET', '/metrics')
  }

  async searchHealth() {
    return this.request<any>('GET', '/search/health')
  }

  // Repositories
  async listRepositories(params?: any) {
    return this.request<any[]>('GET', '/repositories', { params })
  }

  async addRepository(data: any) {
    return this.request<any>('POST', '/repositories', { data })
  }

  async getRepository(id: string) {
    return this.request<any>('GET', `/repositories/${id}`)
  }

  async deleteRepository(id: string) {
    return this.request<any>('DELETE', `/repositories/${id}`)
  }

  async reindexRepository(id: string) {
    return this.request<any>('POST', `/repositories/${id}/reindex`)
  }

  async getIndexStatus(id: string) {
    return this.request<any>('GET', `/repositories/${id}/index/status`)
  }

  // Context & Retrieval
  async getContext(repoId: string, data: any) {
    return this.request<any>('POST', `/repositories/${repoId}/context`, { data })
  }

  // Prompts
  async buildPrompt(repoId: string, data: any) {
    return this.request<any>('POST', `/repositories/${repoId}/prompt`, { data })
  }

  // Patches
  async generatePatch(repoId: string, data: any) {
    return this.request<any>('POST', `/repositories/${repoId}/patch`, { data })
  }

  async applyPatch(repoId: string, data: any) {
    return this.request<any>('POST', `/repositories/${repoId}/apply-patch`, { data })
  }

  async segmentPatch(repoId: string, patch: string) {
    return this.request<any>('POST', `/repositories/${repoId}/patch/segment`, { data: { patch } })
  }

  // Search
  async searchCode(data: any) {
    return this.request<any>('POST', '/search/code', { data })
  }

  // Recommendations
  async getRecommendations(data: any) {
    return this.request<any>('POST', '/recommendations', { data })
  }

  async interactiveRecommendations(data: any) {
    return this.request<any>('POST', '/recommendations/interactive', { data })
  }

  async refineRecommendations(data: any) {
    return this.request<any>('POST', '/recommendations/refine', { data })
  }

  async submitRecommendationFeedback(sessionId: string, repoId: string, data: any) {
    return this.request<any>('POST', `/recommendations/${sessionId}/feedback`, { 
      params: { repo_id: repoId },
      data 
    })
  }

  // Features & Product
  async listFeatures(repoId: string, params?: any) {
    return this.request<any>('GET', `/features/${repoId}`, { params })
  }

  async listAnalyses(repoId: string, agentRole?: string) {
    return this.request<any>('GET', `/features/${repoId}/analyses`, { 
      params: agentRole ? { agent_role: agentRole } : undefined 
    })
  }

  async triggerProductAnalysis(repoId: string, skipFeatureExtraction = false) {
    return this.request<any>('POST', `/features/${repoId}/analyze`, {
      data: { repo_id: repoId, skip_feature_extraction: skipFeatureExtraction }
    })
  }

  async listSuggestions(repoId: string, params?: any) {
    return this.request<any>('GET', `/features/${repoId}/suggestions`, { params })
  }

  async getSuggestionDetail(repoId: string, suggestionId: string) {
    return this.request<any>('GET', `/features/${repoId}/suggestions/${suggestionId}`)
  }

  async updateSuggestionStatus(repoId: string, suggestionId: string, status: string) {
    return this.request<any>('POST', `/features/${repoId}/suggestions/${suggestionId}/status`, {
      params: { status }
    })
  }

  // Graphs & Dependencies
  async getGraph(repoId: string, type: string, format = 'json', nodeFilter = '', depth = 0) {
    const params: any = { type, format }
    if (nodeFilter) params.node_filter = nodeFilter
    if (depth) params.depth = depth
    return this.request<any>('GET', `/repositories/${repoId}/graphs`, { params })
  }

  async getGraphSummary(repoId: string) {
    return this.request<any>('GET', `/repositories/${repoId}/graphs/summary`)
  }

  async reloadGraphs(repoId: string) {
    return this.request<any>('POST', `/repositories/${repoId}/graphs/reload`)
  }

  async getDependencies(filePath: string, repoId: string, depth = 2, direction = 'both', format = 'json') {
    const encoded = encodeURIComponent(filePath)
    return this.request<any>('GET', `/dependencies/${encoded}`, {
      params: { repository_id: repoId, depth, direction, format }
    })
  }

  // Entity & File Metadata
  async getEntity(repoId: string, entityId: string) {
    return this.request<any>('GET', `/repositories/${repoId}/entities/${entityId}`)
  }

  async getFileMetadata(repoId: string, filePath: string) {
    const encoded = filePath.split('/').map(encodeURIComponent).join('/')
    return this.request<any>('GET', `/repositories/${repoId}/files/${encoded}/metadata`)
  }

  async getSymbolDefinition(repoId: string, symbolName: string, contextFile?: string) {
    return this.request<any>('GET', `/repositories/${repoId}/symbols/definition`, {
      params: { symbol_name: symbolName, context_file: contextFile }
    })
  }

  async getSymbolUsages(repoId: string, symbolName: string) {
    return this.request<any>('GET', `/repositories/${repoId}/symbols/usages`, {
      params: { symbol_name: symbolName }
    })
  }

  // Tests
  async getTestCoverage(repoId: string, filePath?: string, functionName?: string) {
    return this.request<any>('GET', `/repositories/${repoId}/tests/coverage`, {
      params: { file_path: filePath, function_name: functionName }
    })
  }

  async selectTests(repoId: string, data: any) {
    return this.request<any>('POST', `/repositories/${repoId}/tests/select`, { data })
  }

  async runTests(repoId: string, data: any) {
    return this.request<any>('POST', `/repositories/${repoId}/tests/run`, { data })
  }

  // Impact Analysis
  async analyzeImpact(data: any) {
    return this.request<any>('POST', '/impact-analysis', { data })
  }

  // Runner Validation
  async validateWithRunner(data: any) {
    return this.request<any>('POST', '/runner/validate', { data })
  }

  async getValidationStatus(runId: string) {
    return this.request<any>('GET', `/runner/validate/${runId}`)
  }

  // Python Tracing
  async tracePython(repoId: string, data: any) {
    return this.request<any>('POST', `/repositories/${repoId}/trace/python`, { data })
  }

  // Agent Feedback
  async submitExecutionFeedback(data: any) {
    return this.request<any>('POST', '/agent/feedback/execution', { data })
  }

  async submitChangeFeedback(data: any) {
    return this.request<any>('POST', '/agent/feedback/change', { data })
  }

  async getFeedbackSummary(repoId?: string, feedbackType?: string) {
    return this.request<any>('GET', '/agent/feedback/summary', {
      params: { repo_id: repoId, feedback_type: feedbackType }
    })
  }

  async getRetrievalProfile(repoId: string) {
    return this.request<any>('GET', '/agent/feedback/profile', {
      params: { repo_id: repoId }
    })
  }

  // Strategy & Task Analysis
  async analyzeTask(data: any) {
    return this.request<any>('POST', '/api/analyze/task', { data })
  }

  async quickClassifyTask(data: any) {
    return this.request<any>('POST', '/api/analyze/quick-classify', { data })
  }

  async selectStrategy(data: any) {
    return this.request<any>('POST', '/api/strategy/select', { data })
  }

  async getStrategyRules() {
    return this.request<any>('GET', '/api/strategy/rules')
  }

  // Orchestration
  async executeOrchestration(data: any) {
    return this.request<any>('POST', '/api/orchestrate/execute', { data })
  }

  async getOrchestrationStatus(executionId: string) {
    return this.request<any>('GET', `/api/orchestrate/status/${executionId}`)
  }

  async listOrchestrations(repoId?: string) {
    return this.request<any>('GET', '/api/orchestrate/executions', {
      params: repoId ? { repo_id: repoId } : undefined
    })
  }
}

export const api = new ApiService()