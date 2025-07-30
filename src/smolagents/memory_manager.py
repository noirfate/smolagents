"""
记忆管理器 - 基于Planning周期的智能记忆压缩
利用smolagents现有的planning机制作为记忆分割点
"""

from typing import List
from .models import ChatMessage, MessageRole
from .memory import MemoryStep, ActionStep, PlanningStep

__all__ = [
    "MemoryManager"
]


class MemoryManager:
    """轻量级记忆管理器，基于Planning周期进行记忆压缩"""
    
    def __init__(self):
        self._compressed_history = None  # 缓存压缩结果
        self._last_compressed_index = -1  # 记录上次压缩的位置
    
    def get_last_planning_step_index(self, memory_steps: List[MemoryStep]) -> int:
        """找到最后一个PlanningStep的位置"""
        for i in reversed(range(len(memory_steps))):
            if isinstance(memory_steps[i], PlanningStep):
                return i
        return -1
    
    def should_compress(self, memory_steps: List[MemoryStep], agent) -> bool:
        """判断是否需要进行记忆压缩"""
        last_plan_idx = self.get_last_planning_step_index(memory_steps)
        
        # 至少要有两个planning step才考虑压缩
        if last_plan_idx <= 0:
            return False
        
        # 如果已经压缩过，且没有新的planning step，则不需要重复压缩
        if last_plan_idx <= self._last_compressed_index:
            return False
        
        # 使用agent的planning_interval来判断是否有足够的历史需要压缩
        # 如果planning_interval为None，使用默认值5
        planning_interval = agent.planning_interval or 5
        
        # 检查是否有足够的历史需要压缩（至少一个planning_interval的步数）
        return last_plan_idx >= planning_interval
    
    def compress_historical_steps(self, historical_steps: List[MemoryStep], model) -> str:
        """将历史步骤压缩为结构化总结，失败时返回None"""
        if not historical_steps:
            return None
        
        # 构建完整的历史执行信息
        execution_log = []
        
        for i, step in enumerate(historical_steps, 1):
            if isinstance(step, ActionStep):
                step_info = f"**Step {i}** (ActionStep):\n"
                
                # 完整的工具调用信息
                if step.tool_calls:
                    step_info += "  Tool calls:\n"
                    for tc in step.tool_calls:
                        step_info += f"    - {tc.name}({tc.arguments})\n"
                
                # 完整的观察结果
                if step.observations:
                    step_info += f"  Observations: {step.observations}\n"
                
                # 错误信息
                if step.error:
                    step_info += f"  ⚠️ Error: {step.error}\n"
                
                execution_log.append(step_info)
            
            elif isinstance(step, PlanningStep):
                step_info = f"**Step {i}** (PlanningStep):\n"
                step_info += f"  Plan: {step.plan}\n"
                execution_log.append(step_info)
        
        full_log = "\n".join(execution_log)
        
        # 优化的压缩提示，结合smolagents设计理念
        prompt = f"""You are a memory compression assistant for an intelligent agent. Please compress the following execution history into a structured summary.

**Smolagents Design Philosophy**:
- Tool-based problem solving
- Planning → Execution → Observation → Learning cycles
- Multi-step reasoning and tool collaboration
- Learning from errors and adjusting strategies

**Execution history to compress**:
{full_log}

**Compression requirements**:
Please generate a structured execution summary with the following sections:

1. **Solution Path Overview**: Brief description of the overall problem-solving approach and strategy
2. **Key Tool Usage**: List the main tools used and their roles (preserve logical relationships between tool calls)
3. **Important Discoveries**: Summarize key information, data, or conclusions obtained
4. **Strategy Adjustments**: Record mental shifts and method changes when encountering problems
5. **Unresolved Issues**: List problems or questions that still need to be addressed
6. **Experience Gained**: Lessons learned from both successes and failures

**Format requirements**:
- Maintain accuracy and completeness of information
- Highlight the logical chain of tool usage
- Preserve important data and conclusions
- Be concise but retain key details
- Make it useful for subsequent reasoning

Please begin the compression summary:"""

        try:
            messages = [ChatMessage(role=MessageRole.USER, content=prompt)]
            response = model.generate(messages)
            
            if response.content:
                compressed = f"📋 **Execution History Summary** (compressed {len(historical_steps)} steps):\n\n{response.content}"
                return compressed
            else:
                # 模型返回空内容，视为压缩失败
                print(f"⚠️ 记忆压缩失败: 模型返回空内容")
                return None
            
        except Exception as e:
            print(f"⚠️ 记忆压缩失败: {e}")
            return None  # 压缩失败时返回None，让上层方法fallback到原始逻辑
    
    def write_memory_to_messages_with_compression(self, agent, summary_mode: bool = False) -> List[ChatMessage]:
        """带压缩功能的记忆转换方法"""
        memory_steps = agent.memory.steps
        
        # 如果不需要压缩，使用原始方法
        if not self.should_compress(memory_steps, agent):
            return agent._original_write_memory_to_messages(summary_mode)
        
        last_plan_idx = self.get_last_planning_step_index(memory_steps)
        
        # 检查是否需要重新压缩
        if last_plan_idx > self._last_compressed_index:
            # 压缩上次planning之前的历史
            historical_steps = memory_steps[:last_plan_idx]
            compressed_result = self.compress_historical_steps(historical_steps, agent.model)
            
            # 如果压缩失败，fallback到原始方法
            if compressed_result is None:
                print("⚠️ 记忆压缩失败，回退到原始方法以保证历史记录完整性")
                return agent._original_write_memory_to_messages(summary_mode)
            
            self._compressed_history = compressed_result
            self._last_compressed_index = last_plan_idx
        
        # 构建消息
        messages = []
        
        # 1. System prompt
        messages.extend(agent.memory.system_prompt.to_messages(summary_mode))
        
        # 2. 压缩的历史摘要
        if self._compressed_history:
            messages.append(ChatMessage(
                role=MessageRole.ASSISTANT,
                content=[{"type": "text", "text": self._compressed_history}]
            ))
        
        # 3. 最近一个planning周期的完整记录
        recent_steps = memory_steps[last_plan_idx:]
        for step in recent_steps:
            messages.extend(step.to_messages(summary_mode))
        
        return messages