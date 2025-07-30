"""
GitHub工具管理 - 基于MCP协议的GitHub API集成
"""

from typing import List, Optional
from mcp import StdioServerParameters

from .tools import Tool
from .mcp_client import MCPClient

__all__ = ["GitHubTools"]


class GitHubTools:
    """GitHub工具管理器 - 基于MCP协议集成GitHub API"""
    
    def __init__(self, github_token: str):
        """初始化GitHub工具管理器
        
        Args:
            github_token: GitHub Personal Access Token
            
        Raises:
            Exception: 如果连接GitHub MCP服务失败
        """
        if not github_token:
            raise ValueError("GitHub token is required")
            
        self.github_token = github_token
        self._mcp_client: Optional[MCPClient] = None
        self._tools: Optional[List[Tool]] = None
        
        # 立即初始化连接
        self._initialize_connection()
    
    def _initialize_connection(self):
        """初始化GitHub MCP服务连接"""
        try:
            print("🔗 正在连接GitHub MCP server...")
            github_mcp_config = StdioServerParameters(
                command="docker", 
                args=[
                    "run", "-i", "--rm", 
                    "-e", f"GITHUB_PERSONAL_ACCESS_TOKEN={self.github_token}", 
                    "-e", "GITHUB_TOOLSETS=repos,issues,pull_requests", 
                    "ghcr.io/github/github-mcp-server"
                ]
            )
            
            self._mcp_client = MCPClient(github_mcp_config)
            raw_tools = self._mcp_client.get_tools()
            
            self._tools = self._fix_tool_types(raw_tools)
            
            print(f"✅ GitHub MCP server已连接，获得 {len(self._tools)} 个GitHub工具")
            
        except Exception as e:
            print(f"⚠️ 连接GitHub MCP server失败: {e}")
            print(f"   错误类型: {type(e).__name__}")
            raise
    
    def _fix_tool_types(self, tools: List[Tool]) -> List[Tool]:
        """修复GitHub工具类型定义
        
        GitHub MCP server 期望 JSON Schema 的 "number" 类型，但 Python 的 int 会被映射为 "integer" 类型。
        这个方法创建包装器来解决类型不匹配问题。
        
        Args:
            tools: 原始的GitHub工具列表
            
        Returns:
            List[Tool]: 修复类型后的工具列表
        """
        wrapped_tools = []
        
        for tool in tools:
            class GitHubToolWrapper(Tool):
                skip_forward_signature_validation = True  # 跳过签名验证
                
                def __init__(self, original_tool):
                    self.original_tool = original_tool
                    self.name = original_tool.name
                    self.description = original_tool.description
                    self.inputs = original_tool.inputs.copy()
                    self.output_type = original_tool.output_type
                    self.is_initialized = True
                    
                    # 修改 inputs 定义，将 number 类型改为 integer，避免类型验证错误
                    for key, input_def in self.inputs.items():
                        if input_def.get("type") == "number":
                            self.inputs[key] = input_def.copy()
                            self.inputs[key]["type"] = "integer"
                    
                def forward(self, *args, **kwargs):
                    return self.original_tool(*args, **kwargs)
            
            wrapped_tools.append(GitHubToolWrapper(tool))
        
        return wrapped_tools
    
    @property
    def tools(self) -> List[Tool]:
        """获取GitHub工具列表
        
        Returns:
            List[Tool]: GitHub工具列表
        """
        return self._tools or []
    
    def __len__(self) -> int:
        """返回可用工具数量"""
        return len(self._tools) if self._tools else 0