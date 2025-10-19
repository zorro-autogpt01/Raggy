from typing import List, Dict, Protocol
import httpx
import time
import os
from abc import ABC, abstractmethod
from sentence_transformers import SentenceTransformer
import numpy as np
from ..integrations.llm_gateway import LLMGatewayClient
from ..config import settings

class Embedder:
    def __init__(self, model_name: str = "microsoft/codebert-base"):
        """Initialize embedder with specified model"""
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
    
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for single text"""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts (more efficient)"""
        embeddings = self.model.encode(texts, convert_to_numpy=True, batch_size=32)
        return embeddings.tolist()
    
    def embed_code_entity(self, entity: Dict) -> Dict:
        """Generate embedding for a code entity (function/class)"""
        text_parts = []
        
        if 'name' in entity:
            text_parts.append(f"Function: {entity['name']}")
        
        if 'docstring' in entity and entity['docstring']:
            text_parts.append(entity['docstring'])
        
        if 'code' in entity:
            code = entity['code'][:1000]
            text_parts.append(code)
        
        combined_text = "\n".join(text_parts)
        embedding = self.embed_text(combined_text)
        
        return {
            **entity,
            'embedding': embedding,
            'embedding_text': combined_text[:200]
        }

class LLMGatewayEmbedder:
    """
    Embedder that uses your LLM Gateway's embeddings endpoint
    """
    def __init__(
        self,
        gateway_url: str = None,
        model: str = "text-embedding-3-small",
        model_id: int = None,
        model_key: str = None,
        dimensions: int = None
    ):
        self.gateway_url = gateway_url or os.getenv(
            "LLM_GATEWAY_URL", 
            "http://llm-gateway:3010"
        )
        self.model = model
        self.model_id = model_id
        self.model_key = model_key
        self.dimensions = dimensions
        
        self.client = httpx.AsyncClient(
            timeout=60.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        # Simple in-memory memo cache for single texts
        self._memo: Dict[str, tuple[float, List[float]]] = {}
        self._memo_order: List[str] = []

    
    async def embed_texts(self, texts: List[str], max_retries: int = 3) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts with retry logic
        """
        if not texts:
            return []
        
        MAX_CHARS = 8000
        truncated_texts = []
        for text in texts:
            if len(text or "") > MAX_CHARS:
                truncated_texts.append((text or "")[:MAX_CHARS] + "... [truncated]")
            else:
                truncated_texts.append(text or "")
        
        body = {
            "input": truncated_texts,
            "model": self.model
        }
        
        if self.model_id:
            body["model_id"] = self.model_id
        if self.model_key:
            body["model_key"] = self.model_key
        if self.dimensions:
            body["dimensions"] = self.dimensions
        
        last_error = None
        for attempt in range(max_retries):
            try:
                response = await self.client.post(
                    f"{self.gateway_url}/api/embeddings",
                    json=body,
                    timeout=120.0
                )
                response.raise_for_status()
                
                result = response.json()
                embeddings = [item["embedding"] for item in result["data"]]

                # Validate embedding dimensions if provided
                if self.dimensions is not None and embeddings:
                    got = len(embeddings[0])
                    if got != self.dimensions:
                        raise RuntimeError(
                            f"Embedding dimension mismatch: expected {self.dimensions}, got {got}. "
                            "Check LLM gateway model configuration or EMBEDDING_DIMENSION(S) setting."
                        )
                
                return embeddings
                
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 500 and attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1 * (attempt + 1))
                else:
                    raise
            except httpx.TimeoutException as e:
                last_error = e
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    raise
            except Exception as e:
                last_error = e
                break
        
        raise RuntimeError(f"Failed to generate embeddings after {max_retries} attempts: {last_error}")
    
    async def embed_text(self, text: str) -> List[float]:
        """
        Cache single-text embeddings with TTL to reduce gateway calls.
        """
        key = f"{self.model}:{text}"
        now = time.time()
        if settings.embed_cache_enabled:
            ent = self._memo.get(key)
            if ent:
                exp, vec = ent
                if exp > 0 and exp > now:
                    return list(vec)
                else:
                    # expired
                    self._memo.pop(key, None)
                    try:
                        self._memo_order.remove(key)
                    except Exception:
                        pass

        embeddings = await self.embed_texts([text])
        vec = embeddings[0] if embeddings else []
        if settings.embed_cache_enabled and vec:
            exp = now + float(settings.embed_cache_ttl_sec) if settings.embed_cache_ttl_sec > 0 else 0.0
            self._memo[key] = (exp, list(vec))
            self._memo_order.append(key)
            # trim cache size
            max_items = max(10, int(settings.embed_cache_max_items or 256))
            if len(self._memo_order) > max_items:
                to_evict = len(self._memo_order) - max_items
                for _ in range(to_evict):
                    try:
                        oldest = self._memo_order.pop(0)
                        self._memo.pop(oldest, None)
                    except Exception:
                        break
        return vec 
    
    async def close(self):
        await self.client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def embed_code_entity(self, entity: dict) -> dict:
        """Embed a code entity with better error handling"""
        import asyncio
        
        text_parts = []
        
        if entity.get('entity_type'):
            text_parts.append(f"Type: {entity['entity_type']}")
        
        if entity.get('name'):
            text_parts.append(f"Name: {entity['name']}")
        
        if entity.get('file_path'):
            text_parts.append(f"File: {entity['file_path']}")
        
        if entity.get('code'):
            code = entity['code'][:3000]
            text_parts.append(f"Code:\n{code}")
        
        if entity.get('language'):
            text_parts.append(f"Language: {entity['language']}")
        
        text = "\n".join(text_parts)
        
        import re
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        
        if not text.strip():
            text = f"Empty {entity.get('entity_type', 'entity')}"

        MAX_TEXT_LENGTH = 5000
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "... [truncated]"
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        embedding = loop.run_until_complete(self.embed_text(text))

        # Validate embedding dimension strictly
        if self.dimensions is not None and embedding and len(embedding) != self.dimensions:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {self.dimensions}, got {len(embedding)}. "
                "Fix configuration to avoid corrupting the vector store."
            )
        
        entity['embedding'] = embedding
        return entity

class OpenAIEmbedder:
    """
    Direct OpenAI embedder (fallback/alternative)
    """
    def __init__(self, model: str = "text-embedding-3-small"):
        import openai
        self.model = model
        self.client = openai.AsyncOpenAI()
    
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        
        return [item.embedding for item in response.data]
    
    async def embed_text(self, text: str) -> List[float]:
        embeddings = await self.embed_texts([text])
        return embeddings[0] if embeddings else []
