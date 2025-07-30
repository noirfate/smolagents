"""
记忆管理器 - 基于Planning周期的智能记忆压缩
利用smolagents现有的planning机制作为记忆分割点

压缩策略：
- 当有至少2个planning step时，保留最近的{action, plan}组合
- 压缩倒数第二个planning step之前的所有历史
- 结构：system_prompt + compressed_history + recent_{action, plan}
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
    
    def get_planning_step_indices(self, memory_steps: List[MemoryStep]) -> List[int]:
        """一次遍历获取所有PlanningStep的位置"""
        return [i for i, step in enumerate(memory_steps) if isinstance(step, PlanningStep)]
    
    def get_compression_split_point(self, memory_steps: List[MemoryStep]) -> int:
        """获取压缩分割点：直接使用倒数第二个planning step的位置
        
        返回分割点索引，压缩[0:split_point]，保留[split_point:]
        保留部分从完整的planning step开始，包含最近的完整规划周期
        
        边界情况处理：
        - 如果倒数第二个planning step之前没有ActionStep，不进行压缩
        - 确保压缩的部分包含完整的{action, plan}组合
        """
        planning_indices = self.get_planning_step_indices(memory_steps)
        
        # 至少需要两个planning step才能找到倒数第二个
        if len(planning_indices) < 2:
            return -1
        
        second_last_plan_idx = planning_indices[-2]
        
        # 边界情况：检查倒数第二个planning step之前是否有ActionStep
        # 如果没有，说明没有完整的{action, plan}组合可以压缩
        has_action_before_second_last_plan = any(
            isinstance(step, ActionStep) for step in memory_steps[:second_last_plan_idx]
        )
        
        if not has_action_before_second_last_plan:
            return -1  # 不进行压缩
        
        return second_last_plan_idx
    
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
        
        split_point = self.get_compression_split_point(memory_steps)
        
        # 如果没有有效的分割点，使用原始方法
        if split_point < 0:
            return agent._original_write_memory_to_messages(summary_mode)
        
        if split_point > self._last_compressed_index:
            # 压缩分割点之前的历史（保留最近的{action, plan}组合）
            historical_steps = memory_steps[:split_point]
            compressed_result = self.compress_historical_steps(historical_steps, agent.model)
            
            # 如果压缩失败，fallback到原始方法
            if compressed_result is None:
                print("⚠️ 记忆压缩失败，回退到原始方法以保证历史记录完整性")
                return agent._original_write_memory_to_messages(summary_mode)
            
            self._compressed_history = compressed_result
            self._last_compressed_index = split_point
        
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
        
        # 3. 最近的{action, plan}组合及后续记录
        recent_steps = memory_steps[split_point:]
        for step in recent_steps:
            messages.extend(step.to_messages(summary_mode))
        
        return messages