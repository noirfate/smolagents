"""
基于step_callback的实时目标偏离检测
只对update plan进行检测（跳过initial plan），如果偏离则自动纠正
"""

from typing import Optional
from .models import ChatMessage, MessageRole
from .memory import PlanningStep, TaskStep, ActionStep

__all__ = ["GoalDriftCallback"]

class GoalDriftCallback:
    def __init__(self):
        self.initial_request: Optional[str] = None
        
    def __call__(self, memory_step, agent):
        """step_callback接口，在PlanningStep完成后调用"""
        if isinstance(memory_step, PlanningStep):
            if self.initial_request is None:
                self.initial_request = self._extract_initial_request(agent)
            
            # 只检测update plan，跳过initial plan
            if self.initial_request and self._is_update_plan(agent):
                self._check_and_correct_drift(memory_step, agent)
    
    def _extract_initial_request(self, agent) -> Optional[str]:
        """从agent记忆中提取用户初始请求"""
        for step in agent.memory.steps:
            if isinstance(step, TaskStep):
                return step.task
        return None
    
    def _is_update_plan(self, agent) -> bool:
        """判断当前是否为update plan（已有ActionStep执行记录）"""
        for step in agent.memory.steps:
            if isinstance(step, ActionStep):
                return True
        return False
    
    def _check_and_correct_drift(self, planning_step: PlanningStep, agent):
        """检测目标偏离并自动纠正"""
        current_plan = planning_step.plan
        
        # 构建偏离检测prompt
        prompt = f"""You are analyzing whether an AI agent's current plan has drifted from the user's original request.

**User's Original Request:**
{self.initial_request}

**Agent's Current Plan:**
{current_plan}

**Critical Instructions:**
1. Be STRICT: If the plan targets different entities, objects, subjects, or parameters than explicitly requested, it is DRIFTED
2. NO SUBSTITUTIONS: Replacing user-specified items (even with "better" alternatives) without explicit permission is DRIFTED
3. EXACT MATCH REQUIRED: The plan must address the EXACT same entities/subjects the user specified
4. Method variations are ALIGNED, but target variations are DRIFTED

**Analysis Criteria:**
- Does the plan target the EXACT same entities/subjects/objects as the user specified?
- Is the plan addressing the EXACT same question with the EXACT same parameters?
- Any substitution of user-specified targets (IDs, names, numbers, etc.) should be considered DRIFTED

**Required Response Format:**
You MUST respond in exactly this format:

```
STATUS: [ALIGNED|DRIFTED]
EVIDENCE: [Brief factual explanation of your judgment]
CORRECTED_PLAN: [Only if STATUS is DRIFTED - provide the corrected plan here]
```

**Important for CORRECTED_PLAN:**
- The corrected plan MUST follow the same format, structure, and style as the original plan
- Maintain the same level of detail and specificity
- Use similar language patterns and terminology
- Keep the same structural elements (numbering, bullet points, etc.) if present in the original

**Analysis:**"""

        try:
            messages = [ChatMessage(role=MessageRole.USER, content=prompt)]
            response = agent.model.generate(messages)
            
            if response.content:
                self._process_result(response.content, planning_step)
                
        except Exception as e:
            print(f"⚠️ 目标偏离检测失败: {e}")
    
    def _process_result(self, response_content: str, planning_step: PlanningStep):
        """处理检测结果"""
        content = response_content.strip()
        
        # 解析结构化响应
        status, evidence, corrected_plan = self._parse_structured_response(content)
        
        if corrected_plan:
            print("🚨 检测到目标偏离，正在自动纠正...")
            print(f"📋 原计划: {planning_step.plan}")
            print(f"🔄 新计划: {corrected_plan}")
            planning_step.plan = corrected_plan
    
    def _parse_structured_response(self, response_content: str) -> tuple[str, str, Optional[str]]:
        """解析结构化响应，返回(status, evidence, corrected_plan)"""
        status = "UNKNOWN"
        evidence = ""
        corrected_plan = None
        
        lines = response_content.split('\n')
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # 解析STATUS
            if line.startswith("STATUS:"):
                status_value = line.split(":", 1)[1].strip()
                if "ALIGNED" in status_value:
                    status = "ALIGNED"
                elif "DRIFTED" in status_value:
                    status = "DRIFTED"
            
            # 解析EVIDENCE
            elif line.startswith("EVIDENCE:"):
                evidence = line.split(":", 1)[1].strip()
            
            # 解析CORRECTED_PLAN
            elif line.startswith("CORRECTED_PLAN:"):
                plan_content = line.split(":", 1)[1].strip()
                if plan_content:
                    corrected_plan = plan_content
                else:
                    # 如果冒号后没有内容，检查下一行
                    plan_lines = []
                    for j in range(i + 1, len(lines)):
                        next_line = lines[j].strip()
                        if next_line and not next_line.startswith(("STATUS:", "EVIDENCE:", "CORRECTED_PLAN:")):
                            plan_lines.append(next_line)
                        elif next_line.startswith(("STATUS:", "EVIDENCE:", "CORRECTED_PLAN:")):
                            break
                    if plan_lines:
                        corrected_plan = ' '.join(plan_lines)
        
        return status, evidence, corrected_plan