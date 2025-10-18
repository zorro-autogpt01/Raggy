"""
Task Analyzer Implementation
Analyzes code change requests to determine scope, complexity, and strategy
"""

import httpx
import json
import logging
from typing import Optional, List, Dict
from datetime import datetime

from ..api.schemas.task_analyzer_models import (
    TaskAnalysisRequest,
    TaskAnalysis,
    TaskAnalysisResponse,
    create_task_analysis_prompt,
    TASK_ANALYSIS_SYSTEM_PROMPT,
    ComplexityLevel,
    ImpactLevel
)

logger = logging.getLogger(__name__)


class TaskAnalyzer:
    """
    Analyzes tasks to determine what needs to be done
    
    Uses LLM to understand the request and RAG to get codebase context
    """
    
    def __init__(
        self,
        llm_gateway_url: str,
        rag_api_url: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        rag_api_key: Optional[str] = None,
        model: str = "gpt-4o-mini"
    ):
        self.llm_gateway_url = llm_gateway_url
        self.rag_api_url = rag_api_url
        self.llm_api_key = llm_api_key
        self.rag_api_key = rag_api_key
        self.model = model
    
    async def analyze(
        self,
        request: TaskAnalysisRequest,
        use_rag_context: bool = True
    ) -> TaskAnalysisResponse:
        """
        Analyze a task request
        
        Args:
            request: The task to analyze
            use_rag_context: Whether to fetch context from RAG system
        
        Returns:
            TaskAnalysisResponse with analysis or error
        """
        try:
            logger.info(f"Analyzing task for repo {request.repo_id}: {request.task_description[:100]}")
            
            # Step 1: Get repository context from RAG (if available)
            repo_context = None
            file_list = None
            
            if use_rag_context and self.rag_api_url:
                repo_context, file_list = await self._get_rag_context(
                    request.repo_id,
                    request.task_description
                )
            
            # Step 2: Create analysis prompt
            prompt = create_task_analysis_prompt(
                task_description=request.task_description,
                repo_context=repo_context,
                file_list=file_list
            )
            
            # Step 3: Query LLM for analysis
            analysis = await self._analyze_with_llm(prompt)
            
            if not analysis:
                return TaskAnalysisResponse(
                    success=False,
                    error="Failed to analyze task with LLM"
                )
            
            # Step 4: Determine suggested strategy
            suggested_strategy = self._suggest_strategy(analysis)
            
            logger.info(
                f"Task analysis complete: {analysis.task_type} - "
                f"{analysis.complexity} complexity - "
                f"Strategy: {suggested_strategy}"
            )
            
            return TaskAnalysisResponse(
                success=True,
                analysis=analysis,
                suggested_strategy=suggested_strategy
            )
        
        except Exception as e:
            logger.error(f"Task analysis failed: {e}", exc_info=True)
            return TaskAnalysisResponse(
                success=False,
                error=str(e)
            )
    
    async def _get_rag_context(
        self,
        repo_id: str,
        task_description: str
    ) -> tuple[Optional[str], Optional[List[str]]]:
        """
        Get relevant context from RAG system
        
        Returns:
            Tuple of (context_summary, file_list)
        """
        try:
            logger.debug(f"Fetching RAG context for {repo_id}")
            
            async with httpx.AsyncClient() as client:
                headers = {}
                if self.rag_api_key:
                    headers["X-API-Key"] = self.rag_api_key
                
                # Query RAG for relevant context using correct endpoint
                response = await client.post(
                    f"{self.rag_api_url}/search/code",  # ← Updated endpoint
                    json={
                        "repository_id": repo_id,  # ← Updated parameter name
                        "query": task_description,
                        "search_type": "semantic",
                        "max_results": 10  # ← Updated parameter name
                    },
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Extract context summary
                    results = data.get("results", [])
                    if not results and "data" in data:
                        results = data.get("data", [])
                    
                    context_parts = []
                    file_list = set()
                    
                    for result in results:
                        # Try different possible field names
                        file_path = result.get("file_path") or result.get("file") or result.get("path")
                        content = result.get("content", "") or result.get("code", "") or result.get("text", "")
                        
                        if file_path:
                            file_list.add(file_path)
                            context_parts.append(f"File: {file_path}\n{content[:200]}")
                    
                    context_summary = "\n\n".join(context_parts) if context_parts else None
                    
                    logger.info(f"Retrieved context from {len(file_list)} files via RAG")
                    return context_summary, list(file_list)
                
                else:
                    logger.warning(f"RAG API returned {response.status_code}: {response.text[:200]}")
                    return None, None
        
        except Exception as e:
            logger.warning(f"Failed to get RAG context: {e}")
            return None, None
    
    async def _analyze_with_llm(self, prompt: str) -> Optional[TaskAnalysis]:
        """
        Use LLM to analyze the task
        
        Args:
            prompt: The analysis prompt
        
        Returns:
            TaskAnalysis object or None if failed
        """
        try:
            logger.debug(f"Querying LLM for task analysis (model: {self.model})")
            
            async with httpx.AsyncClient() as client:
                headers = {"Content-Type": "application/json"}
                if self.llm_api_key:
                    headers["Authorization"] = f"Bearer {self.llm_api_key}"
                
                response = await client.post(
                    f"{self.llm_gateway_url}/api/v1/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": TASK_ANALYSIS_SYSTEM_PROMPT
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.1,
                        "max_tokens": 2000,
                        "response_format": {"type": "json_object"},
                        "stream": False  # ← Disable streaming!
                    },
                    headers=headers,
                    timeout=60.0
                )
                
                response.raise_for_status()
                result = response.json()
                
                # Extract content - try multiple formats
                content = None
                
                # Format 1: Direct content field
                if "content" in result:
                    content = result["content"]
                
                # Format 2: OpenAI-style choices array
                elif "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0].get("message", {}).get("content", "")
                
                # Format 3: Message object
                elif "message" in result:
                    content = result["message"].get("content", "")
                
                if not content:
                    logger.error(f"No content in LLM response. Response keys: {result.keys()}")
                    logger.debug(f"Full response: {result}")
                    return None
                
                logger.debug(f"LLM response content length: {len(content)}")
                
                # Parse JSON response
                try:
                    analysis_dict = json.loads(content)
                except json.JSONDecodeError:
                    # Try to extract JSON from markdown code blocks
                    import re
                    match = re.search(r'```json\s*(\{.*\})\s*```', content, re.DOTALL)
                    if match:
                        analysis_dict = json.loads(match.group(1))
                    else:
                        logger.error(f"Failed to parse LLM response as JSON: {content[:200]}")
                        return None
                
                # Add metadata
                analysis_dict["llm_model_used"] = self.model
                analysis_dict["analysis_timestamp"] = datetime.utcnow().isoformat() + "Z"
                
                # Create TaskAnalysis object
                analysis = TaskAnalysis(**analysis_dict)
                
                logger.info(
                    f"LLM analysis: {analysis.task_type} - "
                    f"{analysis.complexity} - "
                    f"{analysis.estimated_file_count} files"
                )
                
                return analysis
        
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}", exc_info=True)
            return None
    
    def _suggest_strategy(self, analysis: TaskAnalysis) -> str:
        """
        Suggest direct or branch-based strategy based on analysis
        
        Args:
            analysis: The task analysis
        
        Returns:
            "direct" or "branch"
        """
        # Use the built-in methods from TaskAnalysis
        if analysis.is_simple_change():
            logger.debug("Suggesting direct commit strategy (simple change)")
            return "direct"
        
        if analysis.is_complex_change():
            logger.debug("Suggesting branch-based strategy (complex change)")
            return "branch"
        
        # Edge cases - use heuristics
        
        # Breaking changes always use branch
        if analysis.is_breaking_change:
            return "branch"
        
        # Database migrations always use branch
        if analysis.needs_database_migration:
            return "branch"
        
        # Medium complexity with low impact can be direct
        if (analysis.complexity == ComplexityLevel.MEDIUM and 
            analysis.impact == ImpactLevel.ISOLATED):
            return "direct"
        
        # Default to branch for safety
        logger.debug("Defaulting to branch-based strategy (unclear)")
        return "branch"
    
    async def quick_classify(
        self,
        task_description: str
    ) -> Dict[str, str]:
        """
        Quick classification without full analysis
        
        Useful for fast decision making
        
        Returns:
            Dict with type, complexity, and strategy
        """
        try:
            prompt = f"""Quickly classify this task:

Task: {task_description}

Respond with JSON:
{{
  "type": "feature|fix|refactor|test|docs",
  "complexity": "low|medium|high",
  "strategy": "direct|branch"
}}
"""
            
            async with httpx.AsyncClient() as client:
                headers = {"Content-Type": "application/json"}
                if self.llm_api_key:
                    headers["Authorization"] = f"Bearer {self.llm_api_key}"
                
                response = await client.post(
                    f"{self.llm_gateway_url}/api/v1/chat",
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": "You are a quick task classifier. Respond only with JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.0,
                        "max_tokens": 100,
                        "response_format": {"type": "json_object"},
                        "stream": False  # ← Disable streaming!
                    },
                    headers=headers,
                    timeout=15.0
                )
                
                response.raise_for_status()
                result = response.json()
                
                # Extract content with better error handling
                content = None
                if "content" in result:
                    content = result["content"]
                elif "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0].get("message", {}).get("content", "")
                elif "message" in result:
                    content = result["message"].get("content", "")
                
                if not content:
                    logger.warning(f"No content in quick classify response: {result.keys()}")
                    return {
                        "type": "unknown",
                        "complexity": "medium",
                        "strategy": "branch"
                    }
                
                classification = json.loads(content)
                logger.debug(f"Quick classification: {classification}")
                return classification
        
        except json.JSONDecodeError as e:
            logger.warning(f"Quick classification JSON parse failed: {e}, content: {content if 'content' in locals() else 'N/A'}")
            return {
                "type": "unknown",
                "complexity": "medium",
                "strategy": "branch"
            }
        except Exception as e:
            logger.warning(f"Quick classification failed: {e}")
            return {
                "type": "unknown",
                "complexity": "medium",
                "strategy": "branch"
            }