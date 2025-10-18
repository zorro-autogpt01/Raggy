# examples/simple_agent.py
"""
Example agent that uses CodeContext RAG APIs to implement features
"""
import asyncio
import httpx
from typing import Dict, List, Optional
from datetime import datetime


class CodeContextAgent:
    """Simple agent that can implement features using RAG"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=120.0)
    
    async def implement_feature(
        self,
        repo_id: str,
        task: str,
        max_retries: int = 2
    ) -> Dict:
        """
        Main entry point: implement a feature end-to-end
        
        Steps:
        1. Analyze task and gather context
        2. Find relevant tests
        3. Generate code changes
        4. Apply changes and create PR
        5. Run tests
        6. Provide feedback
        """
        
        print(f"\n{'='*60}")
        print(f"🤖 Agent Task: {task}")
        print(f"{'='*60}\n")
        
        task_id = f"task_{datetime.utcnow().timestamp()}"
        
        # Step 1: Gather context
        print("📚 Step 1: Gathering context...")
        context = await self.gather_context(repo_id, task)
        print(f"   ✓ Retrieved {len(context['chunks'])} code chunks")
        
        # Step 2: Get repository structure
        print("\n🏗️  Step 2: Analyzing repository structure...")
        structure = await self.get_structure(repo_id)
        print(f"   ✓ Found {structure['statistics']['total_files']} files")
        print(f"   ✓ Build system: {structure['build_system']['type']}")
        
        # Step 3: Find related tests
        print("\n🧪 Step 3: Finding related tests...")
        base_files = list(set(c['file_path'] for c in context['chunks'][:3]))
        tests = await self.find_tests(repo_id, base_files)
        print(f"   ✓ Found {len(tests['impacted_tests'])} related tests")
        
        # Step 4: Generate patch
        print("\n⚙️  Step 4: Generating code changes...")
        
        # Build prompt messages from context
        messages = self._build_prompt_messages(task, context, structure)
        
        patch_response = await self.generate_patch(
            repo_id=repo_id,
            task=task,
            messages=messages,
            restrict_to_files=base_files
        )
        
        if not patch_response['validation']['ok']:
            print("   ⚠️  Patch validation failed!")
            print(f"   Issues: {patch_response['validation']['issues']}")
            
            # Provide feedback about failure
            await self.provide_execution_feedback(
                task_id=task_id,
                repo_id=repo_id,
                query=task,
                retrieved_entities=[c['id'] for c in context['chunks']],
                entities_used=[],
                execution_result={"success": False, "reason": "patch_validation_failed"}
            )
            
            return {
                "success": False,
                "reason": "Patch validation failed",
                "details": patch_response['validation']
            }
        
        print(f"   ✓ Generated patch for {len(patch_response['validation']['files'])} files")
        
        # Step 5: Apply patch and create PR
        print("\n🚀 Step 5: Applying changes...")
        
        apply_response = await self.apply_patch(
            repo_id=repo_id,
            patch=patch_response['patch'],
            task=task,
            create_pr=True
        )
        
        if apply_response.get('error'):
            print("   ⚠️  Failed to apply patch")
            
            await self.provide_execution_feedback(
                task_id=task_id,
                repo_id=repo_id,
                query=task,
                retrieved_entities=[c['id'] for c in context['chunks']],
                entities_used=[],
                execution_result={"success": False, "reason": "apply_failed"}
            )
            
            return {
                "success": False,
                "reason": "Apply failed",
                "details": apply_response
            }
        
        print(f"   ✓ Created branch: {apply_response['new_branch']}")
        print(f"   ✓ Commit: {apply_response['commit'][:8]}")
        
        if apply_response.get('pr_created'):
            print(f"   ✓ PR created: {apply_response['pr']['html_url']}")
        
        # Step 6: Run tests
        print("\n🧪 Step 6: Running tests...")
        
        test_results = await self.run_tests(repo_id, tests['impacted_tests'])
        
        success = test_results.get('ok', False)
        
        if success:
            print(f"   ✅ All tests passed!")
        else:
            print(f"   ❌ Some tests failed")
        
        # Step 7: Provide feedback
        print("\n📊 Step 7: Recording feedback...")
        
        await self.provide_change_feedback(
            change_id=apply_response['commit'],
            repo_id=repo_id,
            files_modified=apply_response['summary']['files_changed'],
            dependencies_retrieved=base_files,
            dependencies_actually_affected=apply_response['summary']['files_changed'],
            tests_passed=test_results.get('passed', 0),
            tests_failed=test_results.get('failed', 0),
            success=success
        )
        
        print("   ✓ Feedback recorded\n")
        
        print(f"{'='*60}")
        print(f"{'✅ Task completed successfully!' if success else '⚠️  Task completed with issues'}")
        print(f"{'='*60}\n")
        
        return {
            "success": success,
            "task_id": task_id,
            "branch": apply_response['new_branch'],
            "commit": apply_response['commit'],
            "pr_url": apply_response.get('pr', {}).get('html_url'),
            "tests": test_results
        }
    
    async def gather_context(self, repo_id: str, task: str) -> Dict:
        """Gather code context for task"""
        response = await self.client.post(
            f"/repositories/{repo_id}/context",
            json={
                "query": task,
                "max_chunks": 12,
                "expand_neighbors": True,
                "retrieval_mode": "vector"
            }
        )
        response.raise_for_status()
        return response.json()['data']
    
    async def get_structure(self, repo_id: str) -> Dict:
        """Get repository structure"""
        response = await self.client.get(f"/repositories/{repo_id}/structure")
        response.raise_for_status()
        return response.json()['data']
    
    async def find_tests(self, repo_id: str, modified_files: List[str]) -> Dict:
        """Find tests impacted by files"""
        response = await self.client.post(
            f"/repositories/{repo_id}/tests/select",
            json={"modified_files": modified_files}
        )
        response.raise_for_status()
        return response.json()['data']
    
    async def generate_patch(
        self,
        repo_id: str,
        task: str,
        messages: List[Dict],
        restrict_to_files: Optional[List[str]] = None
    ) -> Dict:
        """Generate code patch"""
        response = await self.client.post(
            f"/repositories/{repo_id}/patch",
            json={
                "query": task,
                "prompt_messages": messages,
                "restrict_to_files": restrict_to_files,
                "force_unified_diff": True,
                "temperature": 0.2
            }
        )
        response.raise_for_status()
        return response.json()['data']
    
    async def apply_patch(
        self,
        repo_id: str,
        patch: str,
        task: str,
        create_pr: bool = True
    ) -> Dict:
        """Apply patch and optionally create PR"""
        response = await self.client.post(
            f"/repositories/{repo_id}/apply-patch",
            json={
                "patch": patch,
                "commit_message": f"feat: {task}",
                "pr_title": task,
                "pr_body": f"Automated implementation of: {task}",
                "create_pr": create_pr,
                "push": True
            }
        )
        response.raise_for_status()
        return response.json()['data']
    
    async def run_tests(self, repo_id: str, tests: List[Dict]) -> Dict:
        """Run tests"""
        test_files = [t['test_file'] for t in tests[:5]]  # Limit
        
        response = await self.client.post(
            f"/repositories/{repo_id}/tests/run",
            json={"tests": test_files}
        )
        response.raise_for_status()
        return response.json()['data']
    
    async def provide_execution_feedback(
        self,
        task_id: str,
        repo_id: str,
        query: str,
        retrieved_entities: List[str],
        entities_used: List[str],
        execution_result: Dict
    ):
        """Provide execution feedback to RAG"""
        await self.client.post(
            "/agent/feedback/execution",
            json={
                "task_id": task_id,
                "repo_id": repo_id,
                "retrieval_query": query,
                "retrieved_entities": retrieved_entities,
                "entities_used": entities_used,
                "execution_result": execution_result
            }
        )
    
    async def provide_change_feedback(
        self,
        change_id: str,
        repo_id: str,
        files_modified: List[str],
        dependencies_retrieved: List[str],
        dependencies_actually_affected: List[str],
        tests_passed: int,
        tests_failed: int,
        success: bool
    ):
        """Provide change feedback to RAG"""
        await self.client.post(
            "/agent/feedback/change",
            json={
                "change_id": change_id,
                "repo_id": repo_id,
                "files_modified": files_modified,
                "dependencies_retrieved": dependencies_retrieved,
                "dependencies_actually_affected": dependencies_actually_affected,
                "blast_radius_predicted": len(dependencies_retrieved),
                "blast_radius_actual": len(dependencies_actually_affected),
                "tests_passed": tests_passed,
                "tests_failed": tests_failed,
                "success": success
            }
        )
    
    def _build_prompt_messages(
        self,
        task: str,
        context: Dict,
        structure: Dict
    ) -> List[Dict]:
        """Build prompt messages from context"""
        
        system_prompt = (
            "You are an expert software engineer. "
            "Implement the requested feature using the provided code context. "
            "Generate only a unified diff patch. No explanations."
        )
        
        # Build context summary
        files_summary = "\n".join([
            f"- {chunk['file_path']} (lines {chunk['start_line']}-{chunk['end_line']})"
            for chunk in context['chunks'][:5]
        ])
        
        code_blocks = "\n\n".join([
            f"File: {chunk['file_path']}\n"
            f"Lines: {chunk['start_line']}-{chunk['end_line']}\n"
            f"```{chunk['language']}\n{chunk['snippet']}\n```"
            for chunk in context['chunks'][:5]
        ])
        
        user_prompt = f"""Task: {task}

Repository Info:
- Build system: {structure['build_system']['type']}
- Languages: {', '.join(structure.get('languages', []))}

Relevant Files:
{files_summary}

Code Context:
{code_blocks}

Generate a unified diff patch to implement this feature.
"""
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    
    async def close(self):
        """Cleanup"""
        await self.client.aclose()


# Example usage
async def main():
    agent = CodeContextAgent(base_url="http://localhost:8000")
    
    try:
        result = await agent.implement_feature(
            repo_id="your_repo_id",
            task="Add user authentication with JWT tokens"
        )
        
        print(f"\n🎉 Result: {result}")
        
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())