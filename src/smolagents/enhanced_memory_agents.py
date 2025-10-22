"""
增强的Agent类 - 集成基于Planning周期的记忆压缩功能
通过继承方式最小侵入地扩展现有Agent
"""

from typing import Generator, List

from .agents import ToolCallingAgent, CodeAgent
from .models import ChatMessage
from .memory_manager import MemoryManager
from .memory import PlanningStep
from .tools import Tool

__all__ = [
    "MemoryCompressedToolCallingAgent",
    "MemoryCompressedCodeAgent",
    "HistorySearchTool",
    "StepContentTool"
]


class HistorySearchTool(Tool):
    """历史步骤搜索工具 - 根据关键词搜索你之前执行的动作"""
    
    name = "search_history_steps"
    description = "根据关键词搜索你之前执行的所有动作步骤（包括工具调用、代码执行等）。返回匹配的步骤编号列表和第一个匹配步骤的完整内容。当你需要回忆之前做过什么、使用过哪些工具、执行过什么代码时，可以使用此工具。"
    inputs = {
        "keyword": {
            "type": "string", 
            "description": "要搜索的关键词，可以是工具名称、变量名、函数名、文件名等任何在执行过程中出现的内容。"
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
                return f"在会话历史中未找到包含关键词 '{keyword}' 的执行步骤。"
            
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
    """步骤内容获取工具 - 查看你在某个步骤中做了什么"""
    
    name = "get_step_content"
    description = "根据步骤编号获取你在该步骤中执行的完整内容，包括调用的工具、执行的代码、输出结果等。通常与 search_history_steps 工具配合使用：先搜索到相关步骤编号，再用此工具查看详细内容。"
    inputs = {
        "step_number": {
            "type": "integer", 
            "description": "要查看的执行步骤编号。可以通过 search_history_steps 工具获得相关步骤的编号。"
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
            return f"获取步骤内容时发生错误: {str(e)}\n提示：请确保使用的步骤编号来自 search_history_steps 工具的搜索结果。"


class MemoryCompressedToolCallingAgent(ToolCallingAgent):
    """集成记忆压缩功能的ToolCallingAgent"""
    
    def __init__(self, *args, memory_dir=".", aggressive_compression=False, **kwargs):
        """初始化 MemoryCompressedToolCallingAgent
        
        Args:
            memory_dir: 记忆文件保存目录
            aggressive_compression: 是否使用激进压缩策略（默认 False）
                - True: 只保留当前 plan 及后续 action，更节省 token
                - False: 保留最近一次完整的 {action, plan} 周期
            **kwargs: 其他参数传递给父类
        """
        super().__init__(*args, **kwargs)
        self.memory_manager = MemoryManager(
            agent=self, 
            memory_dir=memory_dir,
            aggressive_compression=aggressive_compression
        )
        
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
    """集成记忆压缩功能的CodeAgent
    
    包含历史代码追踪功能：在每次 planning 时自动在 plan 文本中追加历史代码执行摘要
    """
    
    def __init__(self, *args, memory_dir=".", aggressive_compression=True, **kwargs):
        """初始化 MemoryCompressedCodeAgent
        
        Args:
            memory_dir: 记忆文件保存目录
            aggressive_compression: 是否使用激进压缩策略（默认 True）
                - True: 只保留当前 plan 及后续 action，更节省 token
                       因为 plan 中已包含历史代码摘要，模型可通过工具查看详细历史
                - False: 保留最近一次完整的 {action, plan} 周期，更保守
            **kwargs: 其他参数传递给父类
        """
        super().__init__(*args, **kwargs)
        self.memory_manager = MemoryManager(
            agent=self, 
            memory_dir=memory_dir,
            aggressive_compression=aggressive_compression
        )
        
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
    
    def _generate_planning_step(
        self, task, is_first_step: bool, step: int
    ) -> Generator:
        """重写 planning 步骤生成方法，在 plan 文本中追加历史代码摘要章节
        
        只在激进压缩策略时追加代码摘要，因为：
        - 激进策略会压缩更多历史，需要在plan中提醒模型可用的变量
        - 保守策略保留了更多上下文，已有足够的历史信息
        """
        # 如果不是激进压缩策略，直接使用父类方法
        if not self.memory_manager.aggressive_compression:
            yield from super()._generate_planning_step(task, is_first_step, step)
            return
        
        # 激进压缩策略：在Plan中追加历史代码摘要
        for event in super()._generate_planning_step(task, is_first_step, step):
            # 保留所有中间事件（如流式输出）
            if isinstance(event, PlanningStep):
                # 如果不是第一次 planning，追加历史代码摘要到 plan 文本
                if not is_first_step:
                    code_summary = self.memory_manager.get_historical_code_summary()
                    if code_summary:
                        event.plan += f"\n\n{code_summary}"
                        
                        # 使用更好的显示格式来输出历史代码摘要
                        from .monitoring import LogLevel
                        from rich.panel import Panel
                        from rich.text import Text
                        
                        # 创建显示内容
                        display_content = Text()
                        display_content.append("📜 ", style="bold cyan")
                        display_content.append("历史代码执行摘要已添加到规划中\n", style="bold cyan")
                        display_content.append("模型现在可以看到之前执行的代码和可复用的变量", style="dim")
                        
                        # 用Panel包装，使其更突出
                        panel = Panel(
                            display_content,
                            title="[bold yellow]💡 CodeAgent激进压缩[/bold yellow]",
                            border_style="cyan",
                            padding=(0, 1)
                        )
                        
                        self.logger.log(panel, level=LogLevel.INFO)
            
            # Yield 所有事件（包括修改后的 PlanningStep）
            yield event
