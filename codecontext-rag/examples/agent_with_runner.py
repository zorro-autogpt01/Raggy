# examples/agent_with_runner.py
"""
Example agent using the test runner for validation
"""
import asyncio
from simple_agent import CodeContextAgent


class ValidatingAgent(CodeContextAgent):
    """Agent that uses runner for validation"""
    
    async def implement_feature_with_validation(
        self,
        repo_id: str,
        task: str,
        wait_for_validation: bool = True
    ):
        """
        Implement feature with runner validation
        
        Workflow:
        1. Generate patch using RAG
        2. Send to runner for validation
        3. Runner validates in sandbox with LLM debug loop
        4. If successful, changes are automatically committed
        """
        
        print(f"\n{'='*60}")
        print(f"🤖 Agent Task (with Runner): {task}")
        print(f"{'='*60}\n")
        
        # Step 1: Gather context and generate patch
        print("📚 Step 1: Gathering context...")
        context = await self.gather_context(repo_id, task)
        
        print("\n⚙️  Step 2: Generating patch...")
        messages = self._build_prompt_messages(task, context, {})
        
        patch_response = await self.generate_patch(
            repo_id=repo_id,
            task=task,
            messages=messages
        )
        
        if not patch_response['validation']['ok']:
            print("   ⚠️  Patch validation failed locally!")
            return {
                "success": False,
                "reason": "Local patch validation failed"
            }
        
        print(f"   ✓ Generated patch for {len(patch_response['validation']['files'])} files")
        
        # Step 3: Send to runner for validation
        print("\n🏃 Step 3: Sending to test runner...")
        
        validation_result = await self.validate_on_runner(
            repo_id=repo_id,
            patch=patch_response['patch'],
            commit_message=f"feat: {task}",
            wait_for_completion=wait_for_validation
        )
        
        if not wait_for_validation:
            print(f"   ✓ Validation started: {validation_result['run_id']}")
            print(f"   → Poll /runner/validate/{validation_result['run_id']} for status")
            return validation_result
        
        # Step 4: Check result
        if validation_result['status'] == 'completed' and validation_result['result']['success']:
            print(f"\n✅ Success!")
            print(f"   Commit: {validation_result['result']['commit'][:8]}")
            print(f"   Attempts: {validation_result['attempts']}")
            
            return {
                "success": True,
                "run_id": validation_result['run_id'],
                "commit": validation_result['result']['commit'],
                "attempts": validation_result['attempts']
            }
        else:
            print(f"\n❌ Validation failed")
            print(f"   Status: {validation_result['status']}")
            print(f"   Attempts: {validation_result['attempts']}")
            if validation_result.get('errors'):
                print(f"   Errors: {validation_result['errors'][-1]}")  # Show last error
            
            return {
                "success": False,
                "run_id": validation_result['run_id'],
                "status": validation_result['status'],
                "attempts": validation_result['attempts']
            }
    
    async def validate_on_runner(
        self,
        repo_id: str,
        patch: str,
        commit_message: str,
        wait_for_completion: bool = True
    ):
        """Send patch to runner for validation"""
        
        response = await self.client.post(
            "/runner/validate",
            json={
                "repo_id": repo_id,
                "patch": patch,
                "commit_message": commit_message,
                "wait_for_completion": wait_for_completion
            }
        )
        response.raise_for_status()
        return response.json()['data']


async def main():
    agent = ValidatingAgent(base_url="http://localhost:8000")
    
    try:
        result = await agent.implement_feature_with_validation(
            repo_id="your_repo_id",
            task="Add user authentication with JWT tokens",
            wait_for_validation=True
        )
        
        if result['success']:
            print(f"\n🎉 Feature implemented and validated!")
            print(f"   Commit: {result['commit']}")
            print(f"   It took {result['attempts']} validation attempt(s)")
        else:
            print(f"\n😞 Feature implementation failed")
            print(f"   Check run details: {result['run_id']}")
        
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())