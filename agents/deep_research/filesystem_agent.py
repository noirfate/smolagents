"""
FilesystemAgent - 文件系统操作专家

结合了shell命令执行和文件系统操作的专业代理，提供完整的文件管理和系统操作能力。
"""

from smolagents import (
    CodeAgent,
    Model
)

# 导入文件系统工具
from smolagents.filesystem_tools import (
    ListDirectoryTool,
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    FileSearchTool,
    FileContentSearchTool,
)

# 导入Shell工具
from smolagents import ShellTools


def create_filesystem_agent(model: Model, max_steps: int = 30) -> CodeAgent:
    """
    创建文件系统操作专家Agent
    
    Args:
        model: LLM模型实例
        max_steps: 最大执行步数
    
    Returns:
        CodeAgent: 配置好的文件系统Agent
    """
    
    # 组合所有文件系统和Shell工具
    filesystem_tools = [
        # 文件系统操作工具
        ListDirectoryTool(),
        ReadFileTool(),
        WriteFileTool(),
        EditFileTool(),
        FileSearchTool(),
        FileContentSearchTool(),
    ]
    
    # Shell工具 - 使用新的封装类
    shell_tools = ShellTools(
        default_page_size=20480,    # 20KB分页大小，超过此大小自动分页
        include_system_info=True    # 包含系统信息工具
    )
    filesystem_tools.extend(shell_tools.tools)
    
    filesystem_agent = CodeAgent(
        model=model,
        tools=filesystem_tools,
        max_steps=max_steps,
        additional_authorized_imports=["*"],
        verbosity_level=2,
        planning_interval=8,
        name="filesystem_agent",
        description="""A specialized team member for file system operations and command execution.
Ask him for all tasks related to:

**File System Operations:**
- Reading, writing, and editing files
- Listing directory contents and searching for files
- Searching content within files (supports wildcards like *.py, test_*)
- File and directory management

**System Commands:**
- Executing shell commands on Windows and Linux/Unix systems
- Getting system information (OS, hardware, Python environment)
- Running scripts and system utilities
- Managing processes and system resources

**Combined Operations:**
- Analyzing codebases and project structures
- Batch file operations and processing
- System administration tasks
- Development environment setup and maintenance

He can handle complex file operations, execute system commands safely, and combine both capabilities for comprehensive system management tasks.
Provide him with specific requests about file operations, system commands, or combined workflows.
""",
    )
    filesystem_agent.prompt_templates["managed_agent"]["task"] += """

**CRITICAL: Final Result Completeness Guidelines**

When providing your FINAL ANSWER to the user, you MUST ensure completeness:

**1. Complete Final Results:**
- Your FINAL ANSWER must include ALL content that directly addresses the user's question
- If the user asks for file content, show the COMPLETE file content in your final answer
- If the user asks for search results, include ALL matches in your final answer
- If the user asks for directory listings, show ALL items in your final answer

**2. Intermediate Steps vs Final Answer:**
- During your work process, you can summarize intermediate steps for efficiency
- But your FINAL ANSWER to the user must be complete and comprehensive
- Don't just say "I found the information" - actually include ALL the information

**3. What Your Final Answer Should Include:**
- ✅ Complete file contents when files are requested
- ✅ All search matches when searching is requested  
- ✅ Full directory listings when directories are explored
- ✅ Complete command outputs when system information is requested
- ✅ All relevant details that answer the user's specific question

**4. Examples of GOOD Final Answers:**
- User asks for config file → Show the ENTIRE config file content
- User asks to find Python files → List ALL Python files found with full paths
- User asks for system info → Include ALL relevant system details
- User asks to search for "TODO" → Show ALL files containing "TODO" with the matching lines

**5. Examples of BAD Final Answers:**
- ❌ "I found your config file and it looks good"
- ❌ "Found 20 Python files in the project"  
- ❌ "System information has been retrieved"
- ❌ "Several files contain TODO comments"

**REMEMBER: Intermediate steps can be efficient, but your final answer must give the user EVERYTHING they asked for. They shouldn't need to ask follow-up questions to get the complete information.**
"""
    
    return filesystem_agent

__all__ = ["create_filesystem_agent"]
