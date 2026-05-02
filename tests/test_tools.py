"""
Test script for Module 4: Tools + MCP

Usage:
    cd agent-basic
    D:\anaconda3\envs\agent-basic\python.exe tests\test_tools.py
"""

import sys
import os
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import BaseTool, ToolRegistry, ToolExecutor
from core.schemas import ToolSpec, ToolCallRequest, ToolResult
from core.errors import ToolExecutionError


def test_abstract_base():
    print("\n" + "=" * 50)
    print("TEST 1: BaseTool is abstract")
    print("=" * 50)
    try:
        BaseTool()
        print("  XX Should have failed!")
    except TypeError as e:
        print(f"  Correctly blocked: {e}")
        print("  OK")


def test_registry():
    print("\n" + "=" * 50)
    print("TEST 2: ToolRegistry")
    print("=" * 50)
    
    # Create a mock tool
    class MockTool(BaseTool):
        @property
        def spec(self) -> ToolSpec:
            return ToolSpec(name="mock_tool", description="A mock tool for testing")
        
        def invoke(self, request: ToolCallRequest) -> ToolResult:
            return ToolResult(tool_name="mock_tool", success=True, output={"result": "ok"})
    
    registry = ToolRegistry()
    tool = MockTool()
    
    # Test register
    registry.register(tool)
    print(f"  Registered: {tool.spec.name}")
    
    # Test get
    retrieved = registry.get("mock_tool")
    print(f"  Retrieved: {retrieved.spec.name}")
    
    # Test list_specs
    specs = registry.list_specs()
    print(f"  Listed {len(specs)} tool(s): {[s.name for s in specs]}")
    
    # Test duplicate registration
    try:
        registry.register(tool)
        print("  XX Should have failed for duplicate!")
    except ToolExecutionError as e:
        print(f"  Correctly caught duplicate: {e.message}")
    
    # Test get non-existent
    try:
        registry.get("nonexistent")
        print("  XX Should have failed for missing tool!")
    except ToolExecutionError as e:
        print(f"  Correctly caught missing: {e.message}")
    
    print("  OK")


def test_executor():
    print("\n" + "=" * 50)
    print("TEST 3: ToolExecutor")
    print("=" * 50)
    
    class MockTool(BaseTool):
        @property
        def spec(self) -> ToolSpec:
            return ToolSpec(name="calc", description="Calculator")
        
        def invoke(self, request: ToolCallRequest) -> ToolResult:
            a = request.args.get("a", 0)
            b = request.args.get("b", 0)
            return ToolResult(
                tool_name="calc",
                success=True,
                output={"sum": a + b},
            )
    
    registry = ToolRegistry()
    registry.register(MockTool())
    
    executor = ToolExecutor(registry)
    
    # Run async execute synchronously for test
    request = ToolCallRequest(tool_name="calc", args={"a": 3, "b": 5})
    result = asyncio.run(executor.execute(request))
    
    print(f"  Tool: {result.tool_name}")
    print(f"  Success: {result.success}")
    print(f"  Output: {result.output}")
    print(f"  Time: {result.execution_time_ms:.1f} ms")
    print("  OK")


async def test_mcp_example_echo():
    print("\n" + "=" * 50)
    print("TEST 4: MCP Example Echo Tool")
    print("=" * 50)
    
    from tools.mcp import MCPServerConfig, MCPServerManager, MCPClient
    from tools.mcp.tool_adapter import MCPToolAdapter
    
    # Path to example_echo server
    echo_dir = Path(__file__).parent.parent / "tools" / "catalog" / "example_echo"
    
    if not echo_dir.exists():
        print(f"  SKIP example_echo not found: {echo_dir}")
        return
    
    config = MCPServerConfig(
        name="example_echo",
        command=["python", "server.py"],
        working_dir=str(echo_dir),
    )
    
    manager = MCPServerManager()
    manager.register_config(config)
    
    print("  Starting MCP server...")
    await manager.start_all()
    
    try:
        client = manager.get_client("example_echo")
        
        # List tools
        print("  Listing tools...")
        tools = await client.list_tools()
        print(f"  Found {len(tools)} tool(s): {[t.name for t in tools]}")
        
        # Call echo tool
        print("  Calling echo tool...")
        result = await client.call_tool("echo", {"text": "hello mcp"})
        print(f"  Result: {result}")
        
        # Test adapter
        if tools:
            adapter = MCPToolAdapter(client, tools[0])
            print(f"  Adapter spec: {adapter.spec.name} - {adapter.spec.description}")
            
            # Invoke via adapter (use async method directly since we're in async context)
            request = ToolCallRequest(tool_name="echo", args={"text": "via adapter"})
            tool_result = await adapter._async_invoke(request)
            print(f"  Adapter result: {tool_result.output}")
        
        print("  OK")
    finally:
        print("  Shutting down MCP server...")
        await manager.shutdown_all()


def main():
    print("\n" + "=" * 60)
    print("MODULE 4 TESTS: Tools + MCP")
    print("=" * 60)
    
    test_abstract_base()
    test_registry()
    test_executor()
    
    # Run MCP test
    try:
        asyncio.run(test_mcp_example_echo())
    except Exception as e:
        print(f"\n  XX MCP test failed: {e}")
    
    print("\n" + "=" * 50)
    print("ALL TESTS COMPLETED")
    print("=" * 50)


if __name__ == "__main__":
    main()
