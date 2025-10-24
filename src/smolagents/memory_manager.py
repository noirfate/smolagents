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
    
    def __init__(self, agent, memory_dir=".", aggressive_compression=True):
        """初始化记忆管理器
        
        Args:
            agent: Agent实例
            memory_dir: 记忆文件保存目录
            aggressive_compression: 是否使用激进压缩策略
                - True（默认）：只保留当前 plan 及其后续 action，更节省 token
                - False：保留最近一次完整的 {action, plan} 周期，更保守
        """
        self._historical_summaries = []  # 保存所有历史摘要
        self._last_compressed_index = 0  # 记录上次压缩到的位置（不包含）
        self.agent = agent  # 保存agent对象引用
        self.aggressive_compression = aggressive_compression  # 压缩策略选项
        
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
    
    def reset(self):
        """重置压缩状态
        
        当Agent的memory被reset时（如managed agents被多次调用），
        需要同步重置MemoryManager的压缩状态，避免旧的摘要污染新任务
        """
        self._historical_summaries = []
        self._last_compressed_index = 0

    def get_planning_step_indices(self, memory_steps: List[MemoryStep]) -> List[int]:
        """一次遍历获取所有PlanningStep的位置"""
        return [i for i, step in enumerate(memory_steps) if isinstance(step, PlanningStep)]
    
    def get_compression_split_point(self, memory_steps: List[MemoryStep]) -> int:
        """【激进策略】获取压缩分割点：只在新PlanningStep出现时触发压缩
        
        关键设计：
        - 只在刚生成新的PlanningStep时触发压缩（即最后一步是PlanningStep）
        - 压缩该PlanningStep之前的所有内容
        - 保留该PlanningStep及其后续步骤
        - 这样可以避免反复触发压缩，只在规划时压缩一次
        
        为什么这样设计：
        - PlanningStep中已包含历史代码摘要，保留完整历史意义不大
        - 只在规划时触发，避免每次ActionStep后都检查压缩
        - 如果最后不是PlanningStep，说明正在执行Action，不压缩
        
        返回分割点索引，压缩[0:split_point]，保留[split_point:]
        """
        # 如果内存为空或只有一步，不压缩
        if len(memory_steps) < 2:
            return -1
        
        # 检查最后一步是否是PlanningStep
        last_step = memory_steps[-1]
        if not isinstance(last_step, PlanningStep):
            # 如果最后一步不是PlanningStep，不触发压缩
            # 这意味着我们正在执行Action阶段，等下次Planning时再压缩
            return -1
        
        # 找到最后一个PlanningStep的位置
        last_plan_idx = len(memory_steps) - 1
        
        # 检查该PlanningStep之前是否有内容需要压缩
        # 至少要有之前的步骤才值得压缩
        if last_plan_idx == 0:
            return -1  # 第一步就是PlanningStep，没有可压缩的内容
        
        # 确认之前存在ActionStep才进行压缩
        has_action_before = any(
            isinstance(step, ActionStep) for step in memory_steps[:last_plan_idx]
        )
        
        if not has_action_before:
            return -1  # 之前没有实际执行的Action，不压缩
        
        # 返回最后一个PlanningStep的索引作为分割点
        # 压缩[0:last_plan_idx]，保留[last_plan_idx:]（即当前的PlanningStep及后续）
        return last_plan_idx
    
    def get_compression_split_point_conservative(self, memory_steps: List[MemoryStep]) -> int:
        """【保守策略】获取压缩分割点：使用倒数第二个planning step的位置
        
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
            for step in memory_steps:
                # 只对执行步骤（ActionStep）使用编号，其他辅助步骤不编号
                if isinstance(step, ActionStep):
                    step_num = step.step_number
                else:
                    step_num = None  # 辅助步骤（如TaskStep、PlanningStep）不使用编号
                
                markdown_content.extend(self._format_step_content(step, step_num))
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
        """基于 Planning 周期的记忆压缩
        
        【新策略】（aggressive_compression=True）：激进压缩，只在PlanningStep时触发
        - 触发时机：只在新的PlanningStep出现时（最后一步是PlanningStep）
        - 压缩内容：将该PlanningStep之前的所有未压缩步骤压缩为摘要
        - 保留内容：当前的PlanningStep及其后续所有步骤
        - 优势：更节省token，避免反复压缩，plan中已包含历史代码摘要
        - 适用场景：长时间运行的CodeAgent任务
        
        【旧策略】（aggressive_compression=False）：保守压缩，保留最近一次完整的 {action, plan} 周期
        - 触发时机：只要有足够的历史步骤就可能触发
        - 压缩内容：将倒数第二个PlanningStep之前的内容压缩
        - 保留内容：最近一次完整的 {action, plan} 周期
        - 优势：保留更多上下文信息
        - 适用场景：需要保持更多历史细节的ToolCallingAgent任务
        """
        memory_steps = self.agent.memory.steps
        
        # 总是保存完整历史到文件
        self.save_history_to_file(memory_steps)
        
        # 只检查从上次压缩位置之后的新步骤
        new_steps = memory_steps[self._last_compressed_index:]
        
        # 如果没有新步骤，根据是否有历史压缩决定使用哪种方法
        if not new_steps:
            if self._historical_summaries:
                return self._build_messages_from_state(memory_steps, summary_mode)
            else:
                return self.agent._original_write_memory_to_messages(summary_mode)
        
        # 根据配置选择压缩策略，检查新步骤中是否需要压缩
        if self.aggressive_compression:
            split_point = self.get_compression_split_point(new_steps)
        else:
            split_point = self.get_compression_split_point_conservative(new_steps)
        
        # 如果没有有效的分割点，不进行新的压缩
        if split_point < 0:
            # 如果从未发生过压缩，使用原始方法
            if not self._historical_summaries:
                return self.agent._original_write_memory_to_messages(summary_mode)
            # 如果已经有历史压缩，使用压缩状态构建
            return self._build_messages_from_state(memory_steps, summary_mode)
        
        # 计算在完整memory_steps中的实际位置
        actual_split_point = self._last_compressed_index + split_point
        
        # 压缩从上次压缩位置到分割点的步骤
        steps_to_compress = memory_steps[self._last_compressed_index:actual_split_point]
        
        if not steps_to_compress:
            # 理论上不应该到这里，但为了安全
            if not self._historical_summaries:
                return self.agent._original_write_memory_to_messages(summary_mode)
            return self._build_messages_from_state(memory_steps, summary_mode)
        
        compressed_result = self.compress_historical_steps(steps_to_compress)
        
        # 如果压缩失败
        if compressed_result is None:
            print("⚠️ 记忆压缩失败，回退到原始方法")
            # 如果这是第一次尝试压缩，回退到原始方法
            if not self._historical_summaries:
                return self.agent._original_write_memory_to_messages(summary_mode)
            # 如果已有历史压缩，使用现有状态
            print("⚠️ 使用已有的压缩状态继续")
            return self._build_messages_from_state(memory_steps, summary_mode)
        
        # 压缩成功，更新状态
        self._historical_summaries.append(compressed_result)
        self._last_compressed_index = actual_split_point
        
        # 构建消息
        return self._build_messages_from_state(memory_steps, summary_mode)
    
    def _build_messages_from_state(self, memory_steps: List[MemoryStep], summary_mode: bool) -> List[ChatMessage]:
        """根据当前压缩状态构建消息列表
        
        Args:
            memory_steps: 完整的内存步骤列表
            summary_mode: 是否使用摘要模式
            
        Returns:
            构建好的消息列表
        """
        messages = []
        
        # 1. System prompt
        messages.extend(self.agent.memory.system_prompt.to_messages(summary_mode))
        
        # 2. 所有历史压缩摘要
        if self._historical_summaries:
            combined_summaries = "\n\n".join(self._historical_summaries)
            messages.append(ChatMessage(
                role=MessageRole.ASSISTANT,
                content=[{"type": "text", "text": f"""{combined_summaries}\n\n---\n\n**注意事项**：已对早期会话历史内容压缩为摘要信息，摘要之前的完整执行历史已保存到文件`{self.memory_file}`中。如果遇到复杂问题需要回溯被压缩的详细执行过程，可使用工具查看该文件。\n\n"""}]
            ))
        
        # 3. 未压缩的步骤（从上次压缩位置到当前）
        uncompressed_steps = memory_steps[self._last_compressed_index:]
        for step in uncompressed_steps:
            messages.extend(step.to_messages(summary_mode))
        
        return messages
    
    def search_steps_by_keyword(self, keyword: str):
        """搜索包含关键词的执行步骤（工具调用、代码执行等）
        
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
        
        for step in memory_steps:
            # 只搜索执行步骤（ActionStep），跳过辅助步骤
            if not isinstance(step, ActionStep):
                continue
            
            step_content = self._get_step_text_content(step)
            
            if keyword in step_content:
                step_number = step.step_number
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
        """根据步骤编号获取执行步骤的完整内容
        
        Args:
            step_number: 执行步骤的编号
            
        Returns:
            str: 步骤的完整内容，包括工具调用、代码执行、输出结果等
        """
        memory_steps = self.agent.memory.steps
        
        # 只在执行步骤（ActionStep）中查找匹配的step_number
        found_step = None
        for step in memory_steps:
            if isinstance(step, ActionStep) and step.step_number == step_number:
                found_step = step
                break
        
        if found_step is None:
            return f"未找到步骤编号 {step_number}。请使用 search_history_steps 工具查找可用的步骤编号。"
        
        return "\n".join(self._format_step_content(found_step, step_number))
    
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
    
    def get_historical_code_summary(self) -> str:
        """提取历史执行的代码，用于在 planning 时提醒模型
        
        只保留最近的 planning_interval * 2 个代码步骤，避免摘要过长。
        如果未设置 planning_interval，默认保留最近 16 个代码步骤。
        
        Returns:
            str: 格式化的历史代码执行摘要
        """
        memory_steps = self.agent.memory.steps
        code_executions = []
        
        # 收集所有代码执行步骤
        for i, step in enumerate(memory_steps):
            if isinstance(step, ActionStep) and step.code_action:
                # 提取代码和执行结果
                code_info = {
                    'step_number': step.step_number,
                    'code': step.code_action,
                    'output': step.action_output,
                    'observations': step.observations,
                    'error': step.error
                }
                code_executions.append(code_info)
        
        if not code_executions:
            return ""
        
        # 只保留最近的 planning_interval * 2 个代码步骤
        # 如果没有设置 planning_interval，默认保留 16 个
        planning_interval = getattr(self.agent, 'planning_interval', None)
        if planning_interval is not None and planning_interval > 0:
            max_code_steps = planning_interval * 2
        else:
            max_code_steps = 16  # 默认值
        
        if len(code_executions) > max_code_steps:
            # 只保留最新的 max_code_steps 个
            code_executions = code_executions[-max_code_steps:]
        
        # 构建摘要
        summary_lines = [
            "**历史代码执行摘要** (用于变量复用):",
            "",
        ]
        
        # 如果代码被截断，添加提示
        # 获取总共有多少代码步骤（从 memory_steps 重新统计）
        total_code_steps = sum(1 for step in self.agent.memory.steps 
                              if isinstance(step, ActionStep) and step.code_action)
        if total_code_steps > max_code_steps:
            summary_lines.append(f"显示最近 {len(code_executions)} 个代码执行步骤（共 {total_code_steps} 个）。如需查看更早的代码，可使用 search_history_steps 工具。")
            summary_lines.append("")
        
        summary_lines.extend([
            "你在之前的步骤中已经执行了以下代码，这些执行产生的变量仍然可用：",
            ""
        ])
        
        for code_info in code_executions:
            summary_lines.append(f"### 步骤 {code_info['step_number']}")
            summary_lines.append("```python")
            summary_lines.append(code_info['code'])
            summary_lines.append("```")
            
            # 添加输出信息（简化版）
            if code_info['observations'] is not None:
                output_str = str(code_info['observations'])
                if len(output_str) > 200:
                    output_str = output_str[:200] + "..."
                    summary_lines.append(f"输出（截断）: `{output_str}`")
                else:
                    summary_lines.append(f"输出: `{output_str}`")
            
            if code_info['error']:
                error_str = str(code_info['error'])
                if len(error_str) > 200:
                    error_str = error_str[:200] + "..."
                    summary_lines.append(f"⚠️ 错误（截断）: {error_str}")
                else:
                    summary_lines.append(f"⚠️ 错误: {error_str}")
            
            summary_lines.append("")
        
        summary_lines.extend([
            "**提示**: ",
            "- 你可以直接使用上述代码中定义的变量和导入的模块",
            "- 无需重复执行已经成功的代码",
            "- 如果之前的执行有错误，你应该避免重复相同的错误",
            "- 可以使用`search_history_steps`和`get_step_content`工具来查看会话历史记录"
            ""
        ])
        
        return "\n".join(summary_lines)
    
    def _format_step_content(self, step, step_number):
        """格式化步骤内容为markdown格式
        
        Args:
            step: 步骤对象
            step_number: 步骤编号（对于执行步骤使用真实编号，对于其他类型传入None）
        """
        markdown_content = []
        
        # 只为执行步骤显示步骤编号
        if step_number is not None:
            markdown_content.append(f"## 步骤 {step_number} - {step.__class__.__name__}")
        else:
            markdown_content.append(f"## {step.__class__.__name__}")
                
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