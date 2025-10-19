
import httpx
from typing import List, Dict, Optional, AsyncIterator, Any
from ..config import settings

class LLMGatewayClient:
    """Client for LLM Gateway API with hardened error handling"""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or settings.llm_gateway_url
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)
    
    async def chat(
        self,
        messages: List[Dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = None,
        stream: bool = False,
        metadata: Dict = None,
        dry_run: bool = False
    ) -> Dict | AsyncIterator[str]:
        """
        Send chat request to LLM Gateway.
        Always returns a dict with at least keys: {"content": str, "error": Optional[str]} when stream=False.
        For stream=True, returns an async iterator of decoded text chunks.
        """
        data = {
            "model": model or settings.llm_gateway_model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            "metadata": metadata or {},
            "dry_run": dry_run
        }
        
        if max_tokens:
            data["max_tokens"] = max_tokens

        if stream:
            # Streamed responses handled via generator
            return self._stream_chat_safe(data)
        else:
            try:
                response = await self.client.post("/api/v1/chat", json=data)
                response.raise_for_status()
                try:
                    payload = response.json()
                except Exception as je:
                    return {"content": "", "error": f"LLM JSON decode failed: {je}"}
                # Normalize to content
                content = ""
                if isinstance(payload, dict):
                    if "content" in payload:
                        content = payload.get("content") or ""
                    elif "choices" in payload and payload["choices"]:
                        content = payload["choices"][0].get("message", {}).get("content", "")
                    elif "message" in payload:
                        content = payload["message"].get("content", "")
                return {"content": content or "", "error": None}
            except httpx.TimeoutException as te:
                return {"content": "", "error": f"LLM timeout: {te}"}
            except httpx.HTTPStatusError as he:
                # include partial gateway error if any
                body = ""
                try:
                    body = he.response.text[:300]
                except Exception:
                    body = ""
                return {"content": "", "error": f"LLM HTTP {he.response.status_code}: {body}"}
            except Exception as e:
                return {"content": "", "error": f"LLM error: {e}"}
    
    async def _stream_chat_safe(self, data: Dict) -> AsyncIterator[str]:
        """
        Stream chat response safely. Yields text chunks; stops on error.
        """
        try:
            async with self.client.stream("POST", "/api/v1/chat", json=data) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    # gateway may send lines like "data: ..."; tolerate raw JSON as well
                    if line.startswith("data: "):
                        chunk = line[6:]
                    else:
                        chunk = line
                    if chunk.strip():
                        yield chunk
        except httpx.TimeoutException:
            # Emit nothing further on timeout; stream ends
            return
        except httpx.HTTPStatusError:
            return
        except Exception:
            return
    
    async def count_tokens(
        self,
        text: str = None,
        messages: List[Dict] = None,
        model: str = None
    ) -> Dict:
        """Count tokens using LLM Gateway with safer parsing"""
        data = {"model": model or settings.llm_gateway_model}
        if text:
            data["text"] = text
        if messages:
            data["messages"] = messages
        try:
            response = await self.client.post("/api/tokens", json=data)
            response.raise_for_status()
            try:
                return response.json()
            except Exception as je:
                return {"error": f"Token count JSON decode failed: {je}"}
        except Exception as e:
            return {"error": f"Token count failed: {e}"}
    
    async def get_embedding(
        self,
        text: str,
        model: str = "text-embedding-3-small"
    ) -> List[float]:
        raise NotImplementedError("Embedding endpoint not yet in LLM Gateway")
    
    async def create_conversation(
        self,
        conversation_id: str,
        title: str = None,
        system_prompt: str = None,
        metadata: Dict = None
    ) -> Dict:
        data = {
            "id": conversation_id,
            "title": title,
            "system_prompt": system_prompt,
            "meta": metadata or {}
        }
        try:
            response = await self.client.post("/api/conversations", json=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": f"create_conversation failed: {e}"}
    
    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Dict = None
    ) -> Dict:
        data = {"role": role, "content": content, "meta": metadata or {}}
        try:
            response = await self.client.post(f"/api/conversations/{conversation_id}/messages", json=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": f"add_message failed: {e}"}
    
    async def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 100
    ) -> List[Dict]:
        params = {"limit": limit}
        try:
            response = await self.client.get(f"/api/conversations/{conversation_id}/messages", params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("items", []) if isinstance(data, dict) else []
        except Exception:
            return []
    
    async def close(self):
        """Close HTTP client"""
        try:
            await self.client.aclose()
        except Exception:
            pass
