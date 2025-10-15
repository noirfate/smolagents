"""
增强的Agent类 - 集成基于Planning周期的记忆压缩功能
通过继承方式最小侵入地扩展现有Agent
"""

from typing import List
from .agents import ToolCallingAgent, CodeAgent
from .models import ChatMessage
from .memory_manager import MemoryManager
from .tools import Tool

__all__ = [
    "MemoryCompressedToolCallingAgent",
    "MemoryCompressedCodeAgent",
    "HistorySearchTool",
    "StepContentTool"
]


class HistorySearchTool(Tool):
    """历史步骤搜索工具 - 根据关键词搜索包含该关键词的所有步骤"""
    
    name = "search_history_steps"
    description = "根据关键词搜索会话历史中包含该关键词的所有步骤。返回匹配的步骤编号列表和第一个匹配步骤的完整内容。"
    inputs = {
        "keyword": {
            "type": "string", 
            "description": "要搜索的关键词，将在所有历史执行步骤的内容中进行匹配。"
        }
    }
    output_type = "string"
    
    def __init__(self, memory_manager):
        super().__init__()
        self.memory_manager = memory_manager
        
    def forward(self, keyword: str) -> str:
        """搜索包含关键词的历史步骤"""
        try:
            if not keyword.strip():
                return "请提供要搜索的关键词。"
            
            result = self.memory_manager.search_steps_by_keyword(keyword)
            
            if result["total_matches"] == 0:
                return f"在会话历史中未找到包含关键词 '{keyword}' 的步骤。"
            
            # 构建返回结果
            response_lines = [
                f"🔍 搜索关键词: '{keyword}'",
                f"📊 找到 {result['total_matches']} 个匹配的步骤: {', '.join(f'步骤{num}' for num in result['matching_steps'])}",
                "",
                "📄 第一个匹配步骤的完整内容:",
                "=" * 50,
                result["first_step_content"]
            ]
            
            # 如果有多个匹配步骤，提示如何查看其他步骤
            if result["total_matches"] > 1:
                other_steps = result["matching_steps"][1:]
                response_lines.extend([
                    "",
                    "=" * 50,
                    f"💡 如需查看其他匹配步骤的内容，请使用 get_step_content 工具:",
                    f"   - 其他匹配步骤: {', '.join(f'步骤{num}' for num in other_steps)}",
                ])
            
            return "\n".join(response_lines)
            
        except Exception as e:
            return f"搜索历史步骤时发生错误: {str(e)}"

class StepContentTool(Tool):
    """步骤内容获取工具 - 根据步骤编号获取特定步骤的完整内容"""
    
    name = "get_step_content"
    description = "根据步骤编号获取特定步骤的完整内容。通常与 search_history_steps 工具配合使用，先搜索到相关步骤编号，再获取具体内容。"
    inputs = {
        "step_number": {
            "type": "integer", 
            "description": "要获取内容的步骤编号（从1开始计数）。可以通过 search_history_steps 工具获得相关步骤的编号。"
        }
    }
    output_type = "string"
    
    def __init__(self, memory_manager):
        super().__init__()
        self.memory_manager = memory_manager
        
    def forward(self, step_number: int) -> str:
        """获取指定步骤的完整内容"""
        try:
            if step_number < 1:
                return "步骤编号必须大于0。"
            
            content = self.memory_manager.get_step_content_by_number(step_number)
            
            # 添加标题
            response_lines = [
                f"📋 步骤 {step_number} 的完整内容:",
                "=" * 50,
                content
            ]
            
            return "\n".join(response_lines)
            
        except Exception as e:
            return f"获取步骤内容时发生错误: {str(e)}"


class MemoryCompressedToolCallingAgent(ToolCallingAgent):
    """集成记忆压缩功能的ToolCallingAgent"""
    
    def __init__(self, *args, memory_dir=".", **kwargs):
        super().__init__(*args, **kwargs)
        self.memory_manager = MemoryManager(agent=self, memory_dir=memory_dir)
        
        # 创建历史记录查看工具
        self.history_search_tool = HistorySearchTool(self.memory_manager)
        self.step_content_tool = StepContentTool(self.memory_manager)
        
        # 将工具添加到代理的工具集中
        tools_to_add = [self.history_search_tool, self.step_content_tool]
        
        if hasattr(self, 'tools') and self.tools is not None:
            # 如果工具是字典格式
            if isinstance(self.tools, dict):
                for tool in tools_to_add:
                    self.tools[tool.name] = tool
            # 如果工具是列表格式
            elif isinstance(self.tools, list):
                self.tools.extend(tools_to_add)
        else:
            # 如果没有工具，创建新的工具字典
            self.tools = {tool.name: tool for tool in tools_to_add}
    
    def _original_write_memory_to_messages(self, summary_mode: bool = False) -> List[ChatMessage]:
        """调用父类的原始write_memory_to_messages方法，避免递归"""
        return super().write_memory_to_messages(summary_mode)
    
    def write_memory_to_messages(self, summary_mode: bool = False) -> List[ChatMessage]:
        """覆盖原始方法，添加记忆压缩功能"""
        return self.memory_manager.write_memory_to_messages_with_compression(summary_mode)


class MemoryCompressedCodeAgent(CodeAgent):
    """集成记忆压缩功能的CodeAgent"""
    
    def __init__(self, *args, memory_dir=".", **kwargs):
        super().__init__(*args, **kwargs)
        self.memory_manager = MemoryManager(agent=self, memory_dir=memory_dir)
        
        # 创建历史记录查看工具
        self.history_search_tool = HistorySearchTool(self.memory_manager)
        self.step_content_tool = StepContentTool(self.memory_manager)
        
        # 将工具添加到代理的工具集中
        tools_to_add = [self.history_search_tool, self.step_content_tool]
        
        if hasattr(self, 'tools') and self.tools is not None:
            # 如果工具是字典格式
            if isinstance(self.tools, dict):
                for tool in tools_to_add:
                    self.tools[tool.name] = tool
            # 如果工具是列表格式
            elif isinstance(self.tools, list):
                self.tools.extend(tools_to_add)
        else:
            # 如果没有工具，创建新的工具字典
            self.tools = {tool.name: tool for tool in tools_to_add}
    
    def _original_write_memory_to_messages(self, summary_mode: bool = False) -> List[ChatMessage]:
        """调用父类的原始write_memory_to_messages方法，避免递归"""
        return super().write_memory_to_messages(summary_mode)
    
    def write_memory_to_messages(self, summary_mode: bool = False) -> List[ChatMessage]:
        """覆盖原始方法，添加记忆压缩功能"""
        return self.memory_manager.write_memory_to_messages_with_compression(summary_mode)
