"""
增强的Agent类 - 集成基于Planning周期的记忆压缩功能
通过继承方式最小侵入地扩展现有Agent
"""

from typing import List
from .agents import ToolCallingAgent, CodeAgent
from .models import ChatMessage
from .memory_manager import MemoryManager

__all__ = [
    "MemoryCompressedToolCallingAgent",
    "MemoryCompressedCodeAgent"
]


class MemoryCompressedToolCallingAgent(ToolCallingAgent):
    """集成记忆压缩功能的ToolCallingAgent"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.memory_manager = MemoryManager()
    
    def _original_write_memory_to_messages(self, summary_mode: bool = False) -> List[ChatMessage]:
        """调用父类的原始write_memory_to_messages方法，避免递归"""
        return super().write_memory_to_messages(summary_mode)
    
    def write_memory_to_messages(self, summary_mode: bool = False) -> List[ChatMessage]:
        """覆盖原始方法，添加记忆压缩功能"""
        return self.memory_manager.write_memory_to_messages_with_compression(self, summary_mode)


class MemoryCompressedCodeAgent(CodeAgent):
    """集成记忆压缩功能的CodeAgent"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.memory_manager = MemoryManager()
    
    def _original_write_memory_to_messages(self, summary_mode: bool = False) -> List[ChatMessage]:
        """调用父类的原始write_memory_to_messages方法，避免递归"""
        return super().write_memory_to_messages(summary_mode)
    
    def write_memory_to_messages(self, summary_mode: bool = False) -> List[ChatMessage]:
        """覆盖原始方法，添加记忆压缩功能"""
        return self.memory_manager.write_memory_to_messages_with_compression(self, summary_mode)

