"""
记忆管理器 - 基于Planning周期的智能记忆压缩
利用smolagents现有的planning机制作为记忆分割点

压缩策略：
- 保留所有历次摘要信息，避免重复压缩导致信息丢失
- 将完整会话历史保存到文件中
- 在摘要末尾添加文件路径提示，让模型可以查找完整历史
- 结构：system_prompt + historical_summaries + recent_{action, plan} + file_hint
"""

from datetime import datetime
from pathlib import Path
from typing import List
from .models import ChatMessage, MessageRole
from .memory import MemoryStep, ActionStep, PlanningStep, TaskStep

__all__ = [
    "MemoryManager"
]

class MemoryManager:
    """轻量级记忆管理器，基于Planning周期进行记忆压缩"""
    
    def __init__(self, agent, memory_dir="."):
        self._historical_summaries = []  # 保存所有历史摘要
        self.agent = agent  # 保存agent对象引用
        
        # 会话管理
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(exist_ok=True)
        
        # 文件路径
        agent_name = getattr(agent, 'name', 'unnamed_agent')
        self.memory_file = self.memory_dir / f"{agent_name}_memory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        self.memory_content = ""
    
    def get_memory_file(self):
        return self.memory_file
    
    def get_memory_content(self):
        return self.memory_content

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
        
    def save_history_to_file(self, memory_steps: List[MemoryStep]):
        """将完整的会话历史追加保存到markdown文件"""
        try:
            # 准备markdown内容
            markdown_content = []
            
            markdown_content.append(f"# 会话历史记录\n\n")
            markdown_content.append(f"**总步骤数**: {len(memory_steps)}")
            markdown_content.append("")
            
            # 添加所有步骤
            for i, step in enumerate(memory_steps):
                markdown_content.extend(self._format_step_content(step, i+1))
                markdown_content.append("")
            
            markdown_content.append("---")
            markdown_content.append("")
            
            self.memory_content = '\n'.join(markdown_content)
            # 追加写入文件
            with open(self.memory_file, 'w+', encoding='utf-8') as f:
                f.write(self.memory_content)
                
        except Exception as e:
            print(f"⚠️ 保存会话历史失败: {e}")

        return None
    
    def compress_historical_steps(self, historical_steps: List[MemoryStep]) -> str:
        """将历史步骤压缩为结构化总结"""
        if not historical_steps:
            return None
        
        # 构建执行信息
        execution_log = []
        
        for i, step in enumerate(historical_steps, 1):
            if isinstance(step, ActionStep):
                step_info = f"# ActionStep\n"
                
                # 工具调用信息
                if step.tool_calls:
                    step_info += "## Tool calls\n"
                    for tc in step.tool_calls:
                        step_info += f"- {tc.name}({tc.arguments})\n"
                
                # 观察结果
                if step.observations:
                    step_info += f"## Observations\n{step.observations}\n"
                
                # 错误信息
                if step.error:
                    step_info += f"## Error\n{str(step.error)}\n"
                
                execution_log.append(step_info)
            
            elif isinstance(step, PlanningStep):
                step_info = f"# PlanningStep\n"
                step_info += f"{step.plan}\n"
                execution_log.append(step_info)
            
            execution_log.append("\n---\n")
        
        full_log = "\n".join(execution_log)
        
        # 压缩提示
        prompt = f"""你是一个智能代理的记忆压缩助手。请将以下执行步骤压缩为结构化摘要。

**需要压缩的执行步骤**：

```markdown
{full_log}
```

**压缩要求**：
请生成包含以下部分的结构化执行摘要：

1. **解决方案路径概述**：简要描述这些步骤中的问题解决方法
2. **关键工具使用**：列出使用的主要工具及其作用
3. **重要发现**：总结获得的关键信息、数据或结论
4. **策略调整**：记录思路转变和方法变更
5. **未解决问题**：列出仍需解决的问题或疑问
6. **经验总结**：从成功和失败中获得的经验教训

**格式要求**：
- 保持信息的准确性和完整性
- 突出工具使用的逻辑链
- **保留重要数据和结论**：必须包含具体的事实数据，如：
  * 具体的错误信息、错误代码
  * 具体的文件路径、配置参数
  * 具体的命令、参数、返回值
  * 具体的版本号、端口号、时间戳
  * 具体的URL、API密钥、配置值
  * 具体的执行结果、输出内容
- 简洁但保留关键细节

请开始压缩摘要："""

        try:
            messages = [ChatMessage(role=MessageRole.USER, content=prompt)]
            response = self.agent.model.generate(messages)
            
            if response.content:
                # 添加时间戳和步骤范围信息
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                compressed = f"**Execution Summary** (compressed {len(historical_steps)} steps, {timestamp}):\n\n{response.content}"
                return compressed
            else:
                print(f"⚠️ 记忆压缩失败: 模型返回空内容")
                return None
            
        except Exception as e:
            print(f"⚠️ 记忆压缩失败: {e}")
            return None
    
    def write_memory_to_messages_with_compression(self, summary_mode: bool = False) -> List[ChatMessage]:
        memory_steps = self.agent.memory.steps
        
        self.save_history_to_file(memory_steps)

        split_point = self.get_compression_split_point(memory_steps)
        
        # 如果没有有效的分割点，使用原始方法
        if split_point < 0:
            return self.agent._original_write_memory_to_messages(summary_mode)
        
        # 压缩分割点之前的历史
        historical_steps = memory_steps[:split_point]
        compressed_result = self.compress_historical_steps(historical_steps)
        
        # 如果压缩失败，fallback到原始方法
        if compressed_result is None:
            print("⚠️ 记忆压缩失败，回退到原始方法以保证历史记录完整性")
            return self.agent._original_write_memory_to_messages(summary_mode)
        
        # 将新的摘要添加到历史摘要列表
        self._historical_summaries.append(compressed_result)
        
        # 构建消息
        messages = []
        
        # 1. System prompt
        messages.extend(self.agent.memory.system_prompt.to_messages(summary_mode))
        
        # 2. 所有历史摘要
        if self._historical_summaries:
            combined_summaries = "\n\n".join(self._historical_summaries)
            messages.append(ChatMessage(
                role=MessageRole.ASSISTANT,
                content=[{"type": "text", "text": f"""{combined_summaries}\n\n---\n\n**注意事项**：已对早期会话历史内容压缩为摘要信息，摘要之前的完整执行历史已保存到文件`{self.memory_file}`中。如果遇到复杂问题需要回溯被压缩的详细执行过程，可使用工具查看该文件。\n\n"""}]
            ))
        
        # 3. 最近的{action, plan}组合及后续记录
        recent_steps = memory_steps[split_point:]
        for step in recent_steps:
            messages.extend(step.to_messages(summary_mode))
        
        return messages
    
    def search_steps_by_keyword(self, keyword: str):
        """搜索包含关键词的步骤
        
        Returns:
            dict: {
                "matching_steps": [步骤编号列表],
                "first_step_content": "第一个匹配步骤的完整内容",
                "total_matches": 匹配数量
            }
        """
        if not keyword or not keyword.strip():
            return {
                "matching_steps": [],
                "first_step_content": "",
                "total_matches": 0
            }
        
        memory_steps = self.agent.memory.steps
        matching_steps = []
        first_step_content = ""
        
        for i, step in enumerate(memory_steps):
            step_content = self._get_step_text_content(step)
            
            if keyword in step_content:
                step_number = i + 1
                matching_steps.append(step_number)
                
                # 获取第一个匹配步骤的完整内容
                if not first_step_content:
                    first_step_content = "\n".join(self._format_step_content(step, step_number))
        
        return {
            "matching_steps": matching_steps,
            "first_step_content": first_step_content,
            "total_matches": len(matching_steps)
        }
    
    def get_step_content_by_number(self, step_number: int):
        """根据步骤编号获取步骤内容
        
        Args:
            step_number: 步骤编号（从1开始）
            
        Returns:
            str: 步骤的完整内容
        """
        memory_steps = self.agent.memory.steps
        
        if step_number < 1 or step_number > len(memory_steps):
            return f"步骤编号 {step_number} 无效。当前共有 {len(memory_steps)} 个步骤。"
        
        step = memory_steps[step_number - 1]  # 转换为0索引
        return "\n".join(self._format_step_content(step, step_number))
    
    def _get_step_text_content(self, step):
        """提取步骤的文本内容用于搜索"""
        content_parts = []

        if isinstance(step, ActionStep):
            if step.model_output:
                content_parts.append(step.model_output)
            
            if step.tool_calls:
                for tc in step.tool_calls:
                    content_parts.append(f"{tc.name} {tc.arguments}")
            
            if step.observations:
                content_parts.append(step.observations)
            
        return " ".join(content_parts)
    
    def _format_step_content(self, step, step_number):
        """格式化步骤内容为markdown格式"""
        markdown_content = []
        markdown_content.append(f"## 步骤 {step_number} - {step.__class__.__name__}")
                
        if isinstance(step, TaskStep):
            markdown_content.append("**类型**: TaskStep")
            markdown_content.append("**任务**:")
            markdown_content.append(f"```")
            markdown_content.append(step.task)
            markdown_content.append(f"```")
            
            if step.task_images:
                markdown_content.append(f"**包含图片**: {len(step.task_images)} 张")
                
        elif isinstance(step, ActionStep):
            markdown_content.append("**类型**: ActionStep")
                    
            if step.model_output:
                markdown_content.append("**模型输出**:")
                markdown_content.append(f"```")
                markdown_content.append(step.model_output)
                markdown_content.append(f"```")
                    
            if step.tool_calls:
                markdown_content.append("**工具调用**:")
                for tc in step.tool_calls:
                    markdown_content.append(f"- **{tc.name}**: `{tc.arguments}`")
                    
            if step.observations:
                markdown_content.append("**观察结果**:")
                markdown_content.append(f"```")
                markdown_content.append(step.observations)
                markdown_content.append(f"```")
                    
            if step.error:
                markdown_content.append("**错误**:")
                markdown_content.append(f"```")
                markdown_content.append(str(step.error))
                markdown_content.append(f"```")
                
        elif isinstance(step, PlanningStep):
            markdown_content.append("**类型**: PlanningStep")
            markdown_content.append("**计划**:")
            markdown_content.append(f"```")
            markdown_content.append(step.plan)
            markdown_content.append(f"```")
        
        return markdown_content