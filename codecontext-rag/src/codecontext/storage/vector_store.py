# codecontext-rag/src/codecontext/storage/vector_store.py
import lancedb
from typing import List, Dict, Optional
import pyarrow as pa
import pandas as pd
from datetime import datetime

from ..config import settings


def _is_vector_field(field: pa.Field) -> bool:
    """
    Check if a pyarrow field is a Lance-compatible vector type:
    - FixedSizeList(float32) OR
    - List<FixedSizeList(float32)>
    """
    t = field.type
    try:
        if pa.types.is_fixed_size_list(t):
            return pa.types.is_float32(t.value_type)
        if pa.types.is_list(t) and pa.types.is_fixed_size_list(t.value_type):
            inner = t.value_type
            return pa.types.is_float32(inner.value_type)
    except Exception:
        return False
    return False


class VectorStore:
    """
    LanceDB-backed vector store.

    Robust to pre-existing tables created with incorrect schemas:
    - Prefers a new "code_entities_v2" with a proper vector column.
    - If only legacy "code_entities" exists and is empty, it recreates it correctly.
    - If legacy table exists with data but wrong schema, it creates v2 and uses that.
    """

    def __init__(self, path: str = "./data/lancedb"):
        self.db = lancedb.connect(path)
        self.table_name = None  # resolved in _ensure_tables()
        self._ensure_tables()

    def _create_table(self, name: str, dim: int) -> None:
        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("repo_id", pa.string()),
            pa.field("file_path", pa.string()),
            pa.field("entity_type", pa.string()),  # function, class, file, chunk
            pa.field("name", pa.string()),
            pa.field("code", pa.string()),
            pa.field("language", pa.string()),
            pa.field("start_line", pa.int32()),
            pa.field("end_line", pa.int32()),
            pa.field("chunk_id", pa.string()),
            pa.field("embedding", lancedb.vector(dim)),
        ])
        self.db.create_table(name, schema=schema)

    def _table_has_vector_embedding(self, name: str) -> bool:
        try:
            t = self.db.open_table(name)
            sch = t.schema
            if "embedding" not in sch.names:
                return False
            field = sch.field("embedding")
            return _is_vector_field(field)
        except Exception:
            return False

    def _table_is_empty(self, name: str) -> bool:
        try:
            t = self.db.open_table(name)
            return len(t.query().limit(1).to_list()) == 0
        except Exception:
            return True

    def _ensure_tables(self):
        """
        Decide which table to use and ensure it has a vector-typed embedding column.

        Strategy:
        - If v2 exists -> use it.
        - Else if legacy exists:
            - If legacy has vector-typed embedding -> use legacy.
            - Else if legacy is empty -> drop and recreate legacy correctly -> use legacy.
            - Else -> create v2 correctly and use v2 (leave legacy as-is for manual cleanup).
        - Else -> create legacy correctly and use it.
        """
        dim = settings.embedding_dimensions or 1536
        legacy = "code_entities"
        v2 = "code_entities_v2"
        tables = set(self.db.table_names())

        # Prefer v2 if present
        if v2 in tables:
            # Validate vector column; recreate if empty and wrong
            if not self._table_has_vector_embedding(v2):
                if self._table_is_empty(v2):
                    try:
                        try:
                            self.db.drop_table(v2)
                        except Exception:
                            pass
                        self._create_table(v2, dim)
                        print(f"Recreated empty '{v2}' with proper vector schema.")
                    except Exception as e:
                        print(f"Failed to recreate '{v2}': {e}")
                else:
                    print(f"Warning: '{v2}' exists but embedding column is not vector-typed and table has data.")
            self.table_name = v2
            return

        # Handle legacy table
        if legacy in tables:
            if self._table_has_vector_embedding(legacy):
                self.table_name = legacy
                return
            # Legacy exists but not vector-typed
            empty = self._table_is_empty(legacy)
            if empty:
                print("Legacy 'code_entities' exists but is empty and not vector-typed; recreating.")
                try:
                    try:
                        self.db.drop_table(legacy)
                    except Exception:
                        pass
                    self._create_table(legacy, dim)
                    self.table_name = legacy
                    return
                except Exception as e:
                    print(f"Failed to recreate legacy table: {e}")

            # Non-empty and wrong schema: create v2 and use it
            print("Existing legacy table contains data with non-vector embedding. "
                  "Creating and using 'code_entities_v2'. You may re-index repos to populate it.")
            try:
                self._create_table(v2, dim)
                self.table_name = v2
                return
            except Exception as e:
                # As a last resort, still use legacy to avoid None; searches will fail but at least it's explicit
                print(f"Failed to create '{v2}': {e}")
                self.table_name = legacy
                return

        # No tables at all: create legacy fresh
        self._create_table(legacy, dim)
        self.table_name = legacy

    # ------------------- Public API -------------------

    def upsert(self, entities: List[Dict]):
        """Upsert entities to the resolved table with correct vector schema handling."""
        if not entities:
            return

        # Determine embedding dimension from first valid entity
        first = next((e for e in entities if isinstance(e.get("embedding"), list) and e["embedding"]), None)
        if not first:
            print("No valid entities to upsert")
            return
        first_dim = len(first["embedding"])

        valid_entities: List[Dict] = []
        for entity in entities:
            embedding = entity.get('embedding')
            if not embedding or not isinstance(embedding, list):
                print(f"Warning: Skipping entity {entity.get('id')} - no embedding")
                continue
            if len(embedding) != first_dim:
                print(f"Warning: Skipping entity {entity.get('id')} - wrong dimension: {len(embedding)} vs {first_dim}")
                continue
            # Normalize optional fields
            entity.setdefault('name', entity.get('name') or '')
            entity.setdefault('code', entity.get('code') or '')
            entity.setdefault('chunk_id', entity.get('chunk_id') or '')
            valid_entities.append(entity)

        if not valid_entities:
            print("No valid entities to upsert")
            return

        df = pd.DataFrame(valid_entities)

        # Ensure current table has a vector-typed embedding; if not (and empty), recreate
        if not self._table_has_vector_embedding(self.table_name):
            if self._table_is_empty(self.table_name):
                try:
                    try:
                        self.db.drop_table(self.table_name)
                    except Exception:
                        pass
                    self._create_table(self.table_name, first_dim)
                    print(f"Recreated empty '{self.table_name}' with correct vector schema during upsert.")
                except Exception as e:
                    # Fall back to v2 if possible
                    new_table = "code_entities_v2"
                    try:
                        self._create_table(new_table, first_dim)
                        self.table_name = new_table
                        print(f"Switched to '{new_table}' with proper vector schema during upsert.")
                    except Exception as e2:
                        print(f"Failed to recreate a vector table for upsert: {e}; secondary error: {e2}")

        # Try to add rows
        try:
            table = self.db.open_table(self.table_name)
            table.add(df)
        except Exception as e:
            # Table might exist with wrong schema and is not empty; switch to v2
            print(f"VectorStore.upsert add failed on '{self.table_name}': {e}")
            fallback = "code_entities_v2"
            try:
                if fallback not in set(self.db.table_names()):
                    self._create_table(fallback, first_dim)
                self.table_name = fallback
                table = self.db.open_table(self.table_name)
                table.add(df)
                print(f"Upserted into fallback table '{self.table_name}'.")
            except Exception as e2:
                print(f"Upsert failed for fallback table '{fallback}': {e2}")

    def search(
        self,
        embedding: List[float],
        k: int = 10,
        filters: Optional[Dict] = None
    ) -> List[Dict]:
        """Semantic search for similar code entities."""
        table = self.db.open_table(self.table_name)
        # Explicitly specify the vector column to avoid inference errors
        query = table.search(embedding, vector_column_name="embedding").limit(k)

        if filters:
            if 'repo_id' in filters:
                query = query.where(f"repo_id = '{filters['repo_id']}'")
            if 'language' in filters:
                query = query.where(f"language = '{filters['language']}'")
            if 'entity_type' in filters:
                query = query.where(f"entity_type = '{filters['entity_type']}'")
            if 'file_path' in filters:
                query = query.where(f"file_path = '{filters['file_path']}'")

        return query.to_list()

    def get_by_id(self, entity_id: str) -> Optional[Dict]:
        """Fetch a single entity by ID using server-side filtering."""
        table = self.db.open_table(self.table_name)
        try:
            res = table.query().where(f"id = '{entity_id}'").limit(1).to_list()
            return res[0] if res else None
        except Exception as e:
            print(f"VectorStore.get_by_id error: {e}")
            return None

    def query_where(self, where: str, limit: Optional[int] = None) -> List[Dict]:
        """Generic WHERE query helper."""
        table = self.db.open_table(self.table_name)
        try:
            q = table.query().where(where)
            if limit:
                q = q.limit(limit)
            return q.to_list()
        except Exception as e:
            print(f"VectorStore.query_where error: {e}")
            return []

    def get_by_file(self, repo_id: str, file_path: str) -> List[Dict]:
        """Get all entities in a specific file using server-side filtering."""
        table = self.db.open_table(self.table_name)
        try:
            where = f"repo_id = '{repo_id}' AND file_path = '{file_path}'"
            return table.query().where(where).to_list()
        except Exception as e:
            print(f"VectorStore.get_by_file error: {e}")
            return []

    def delete_repository(self, repo_id: str) -> None:
        """Delete all entities for a repository."""
        table = self.db.open_table(self.table_name)
        table.delete(f"repo_id = '{repo_id}'")

    def delete_by_file(self, repo_id: str, file_path: str) -> None:
        """Delete all entities for a specific file."""
        table = self.db.open_table(self.table_name)
        table.delete(f"repo_id = '{repo_id}' AND file_path = '{file_path}'")

    def count_entities(self, repo_id: str) -> int:
        """Count total entities for a repository (filtered server-side)."""
        table = self.db.open_table(self.table_name)
        try:
            ids = table.query().where(f"repo_id = '{repo_id}'").select(["id"]).to_list()
            return len(ids)
        except Exception as e:
            print(f"VectorStore.count_entities error: {e}")
            return 0