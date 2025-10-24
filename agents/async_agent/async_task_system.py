"""
基于任务队列的异步执行系统
不修改原有代码，通过任务队列和后台线程实现异步调用
"""

import threading
import time
import uuid
import queue
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from smolagents import Tool

# OpenTelemetry context propagation
try:
    from opentelemetry import context, trace
    from opentelemetry.context import Context
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    Context = None


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 待执行
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 执行失败


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    task_type: str  # "tool" 或 "managed_agent"
    target_name: str  # 工具名或agent名
    arguments: Dict[str, Any]
    status: TaskStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Any = None
    error: Optional[str] = None
    otel_context: Any = None  # 存储 OpenTelemetry context
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['status'] = self.status.value
        # 不序列化 otel_context，因为它不能被序列化
        data.pop('otel_context', None)
        return data


class TaskManager:
    """任务管理器 - 管理任务队列和执行结果"""
    
    def __init__(self, max_workers: int = 5):
        """
        初始化任务管理器
        
        Args:
            max_workers: 最大工作线程数
        """
        self.task_queue: queue.Queue = queue.Queue()
        self.task_results: Dict[str, TaskInfo] = {}
        self.tools: Dict[str, Tool] = {}
        self.managed_agents: Dict[str, Any] = {}
        
        # 线程池和控制
        self.max_workers = max_workers
        self.executor: Optional[ThreadPoolExecutor] = None
        self.running = False
        self._lock = threading.Lock()
        
        # 统计信息
        self.total_submitted = 0
        self.total_completed = 0
        self.total_failed = 0
    
    def register_tools(self, tools: Dict[str, Tool]):
        """注册可用的工具"""
        with self._lock:
            self.tools.update(tools)
    
    def register_managed_agents(self, managed_agents: Dict[str, Any]):
        """注册可用的managed agents，同时保存初始化参数用于克隆"""
        with self._lock:
            self.managed_agents.update(managed_agents)
            # 保存每个 agent 的初始化信息，用于创建副本
            if not hasattr(self, '_agent_init_params'):
                self._agent_init_params = {}
            
            for name, agent in managed_agents.items():
                # 提取 agent 的初始化参数
                init_params = self._extract_agent_init_params(agent)
                self._agent_init_params[name] = init_params
    
    def _extract_agent_init_params(self, agent) -> Dict[str, Any]:
        """提取 agent 的初始化参数"""
        params = {}
        
        # 基础参数（从实例属性提取）
        if hasattr(agent, 'tools'):
            params['tools'] = agent.tools if isinstance(agent.tools, list) else list(agent.tools.values())
        if hasattr(agent, 'model'):
            params['model'] = agent.model
        if hasattr(agent, 'prompt_templates'):
            params['prompt_templates'] = agent.prompt_templates
        if hasattr(agent, 'instructions'):
            params['instructions'] = agent.instructions
        if hasattr(agent, 'max_steps'):
            params['max_steps'] = agent.max_steps
        if hasattr(agent, 'managed_agents'):
            params['managed_agents'] = list(agent.managed_agents.values()) if isinstance(agent.managed_agents, dict) else agent.managed_agents
        if hasattr(agent, 'planning_interval'):
            params['planning_interval'] = agent.planning_interval
        if hasattr(agent, 'name'):
            params['name'] = agent.name
        if hasattr(agent, 'description'):
            params['description'] = agent.description
        if hasattr(agent, 'provide_run_summary'):
            params['provide_run_summary'] = agent.provide_run_summary
        if hasattr(agent, 'return_full_result'):
            params['return_full_result'] = agent.return_full_result
        if hasattr(agent, 'logger') and hasattr(agent.logger, 'level'):
            params['verbosity_level'] = agent.logger.level
        
        # CodeAgent 特定参数
        if hasattr(agent, 'additional_authorized_imports'):
            params['additional_authorized_imports'] = agent.additional_authorized_imports
        if hasattr(agent, 'max_print_outputs_length'):
            params['max_print_outputs_length'] = agent.max_print_outputs_length
        if hasattr(agent, 'stream_outputs'):
            params['stream_outputs'] = agent.stream_outputs
        if hasattr(agent, '_use_structured_outputs_internally'):
            params['use_structured_outputs_internally'] = agent._use_structured_outputs_internally
        if hasattr(agent, 'code_block_tags'):
            params['code_block_tags'] = agent.code_block_tags
        
        # ToolCallingAgent 特定参数
        if hasattr(agent, 'max_tool_threads'):
            params['max_tool_threads'] = agent.max_tool_threads
        
        # MemoryCompressedCodeAgent/MemoryCompressedToolCallingAgent 特定参数
        if hasattr(agent, 'memory_manager'):
            # 提取记忆压缩相关参数
            if hasattr(agent.memory_manager, 'memory_dir'):
                params['memory_dir'] = str(agent.memory_manager.memory_dir)
            if hasattr(agent.memory_manager, 'aggressive_compression'):
                params['aggressive_compression'] = agent.memory_manager.aggressive_compression
        
        return params
    
    def _create_agent_copy(self, agent_name: str):
        """使用保存的初始化参数创建 agent 的新实例"""
        if agent_name not in self._agent_init_params:
            raise ValueError(f"No init params found for agent '{agent_name}'")
        
        original_agent = self.managed_agents[agent_name]
        init_params = self._agent_init_params[agent_name]
        
        # 获取 agent 的类
        agent_class = original_agent.__class__
        
        # 创建新实例
        try:
            new_agent = agent_class(**init_params)
            return new_agent
        except Exception as e:
            raise RuntimeError(f"Failed to create agent copy: {e}") from e
    
    def start(self):
        """启动任务管理器"""
        if self.running:
            return
            
        self.running = True
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="TaskWorker")
        
        # 启动任务调度线程
        self.scheduler_thread = threading.Thread(target=self._task_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        print(f"✅ TaskManager started with {self.max_workers} workers")
    
    def stop(self):
        """停止任务管理器"""
        if not self.running:
            return
            
        self.running = False
        
        # 停止线程池
        if self.executor:
            self.executor.shutdown(wait=True)
            
        print("🛑 TaskManager stopped")
    
    def submit_task(
        self,
        task_type: str, 
        target_name: str, 
        arguments: Dict[str, Any],
        task_id: Optional[str] = None
    ) -> str:
        """
        提交任务到队列
        
        Args:
            task_type: 任务类型 ("tool" 或 "managed_agent")
            target_name: 目标工具或agent名称
            arguments: 调用参数
            task_id: 可选的任务ID，如果不提供则自动生成
            
        Returns:
            str: 任务ID
        """
        if not self.running:
            raise RuntimeError("TaskManager is not running. Call start() first.")
            
        task_id = task_id or str(uuid.uuid4())
        
        # 验证目标是否存在，并提供友好的错误提示
        if task_type == "tool":
            if target_name not in self.tools:
                # 检查是否误用了 managed_agent 的名称
                if target_name in self.managed_agents:
                    raise ValueError(
                        f"'{target_name}' is a managed agent, not a tool. "
                        f"Please use task_type='managed_agent' instead of 'tool'.\n"
                    )
                else:
                    raise ValueError(
                        f"Tool '{target_name}' not found.\n"
                    )
        elif task_type == "managed_agent":
            if target_name not in self.managed_agents:
                # 检查是否误用了 tool 的名称
                if target_name in self.tools:
                    raise ValueError(
                        f"'{target_name}' is a tool, not a managed agent. "
                        f"Please use task_type='tool' instead of 'managed_agent'.\n"
                    )
                else:
                    raise ValueError(
                        f"Managed agent '{target_name}' not found.\n"
                    )
        else:
            raise ValueError(
                f"Invalid task_type '{task_type}'. Must be 'tool' or 'managed_agent'."
            )
        
        # 捕获当前的 OpenTelemetry context
        otel_ctx = None
        if OTEL_AVAILABLE:
            try:
                otel_ctx = context.get_current()
            except Exception as e:
                print(f"⚠️ Warning: Failed to capture OpenTelemetry context: {e}")
        
        task_info = TaskInfo(
            task_id=task_id,
            task_type=task_type,
            target_name=target_name,
            arguments=arguments,
            status=TaskStatus.PENDING,
            created_at=time.time(),
            otel_context=otel_ctx
        )
        
        with self._lock:
            self.task_results[task_id] = task_info
            self.total_submitted += 1
        
        self.task_queue.put(task_info)
        
        print(f"📤 Task submitted: {task_id} ({task_type}:{target_name})")
        return task_id
    
    def get_task_result(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务结果"""
        with self._lock:
            return self.task_results.get(task_id)
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        task_info = self.get_task_result(task_id)
        return task_info.status if task_info else None
    
    def list_tasks(self, status_filter: Optional[TaskStatus] = None) -> List[TaskInfo]:
        """列出所有任务"""
        with self._lock:
            tasks = list(self.task_results.values())
            if status_filter:
                tasks = [task for task in tasks if task.status == status_filter]
            return sorted(tasks, key=lambda x: x.created_at, reverse=True)
    
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            pending = sum(1 for task in self.task_results.values() if task.status == TaskStatus.PENDING)
            running = sum(1 for task in self.task_results.values() if task.status == TaskStatus.RUNNING)
            
            return {
                "total_submitted": self.total_submitted,
                "total_completed": self.total_completed,
                "total_failed": self.total_failed,
                "pending": pending,
                "running": running,
                "available_tools": list(self.tools.keys()),
                "available_agents": list(self.managed_agents.keys())
            }
    
    def _task_scheduler(self):
        """任务调度器 - 在单独线程中运行"""
        print("🔄 Task scheduler started")
        
        while self.running:
            try:
                # 从队列中获取任务，超时1秒
                task_info = self.task_queue.get(timeout=1.0)
                
                # 提交到线程池执行
                future = self.executor.submit(self._execute_task, task_info)
                
            except queue.Empty:
                # 队列为空，继续循环
                continue
            except Exception as e:
                print(f"❌ Error in task scheduler: {e}")
                traceback.print_exc()
        
        print("🔄 Task scheduler stopped")
    
    def _execute_task(self, task_info: TaskInfo):
        """执行单个任务"""
        task_id = task_info.task_id
        
        # 恢复 OpenTelemetry context（如果存在）
        token = None
        if OTEL_AVAILABLE and task_info.otel_context is not None:
            try:
                token = context.attach(task_info.otel_context)
            except Exception as e:
                print(f"⚠️ Warning: Failed to attach OpenTelemetry context for task {task_id}: {e}")
        
        try:
            # 更新任务状态为执行中
            with self._lock:
                task_info.status = TaskStatus.RUNNING
                task_info.started_at = time.time()
            
            print(f"🔄 Executing task: {task_id}")
            
            # 根据任务类型执行
            if task_info.task_type == "tool":
                tool = self.tools[task_info.target_name]
                if isinstance(task_info.arguments, dict):
                    result = tool(**task_info.arguments)
                else:
                    result = tool(task_info.arguments)
            
            elif task_info.task_type == "managed_agent":
                agent = self._create_agent_copy(task_info.target_name)
                
                if isinstance(task_info.arguments, dict):
                    if 'max_steps' not in task_info.arguments:
                        task_info.arguments['max_steps'] = 20
                    result = agent(**task_info.arguments)
                else:
                    result = agent(task_info.arguments)
            
            else:
                raise ValueError(f"Unknown task type: {task_info.task_type}")
            
            # 更新任务结果
            with self._lock:
                task_info.status = TaskStatus.COMPLETED
                task_info.completed_at = time.time()
                task_info.result = result
                self.total_completed += 1
            
            print(f"✅ Task completed: {task_id}")
            
        except UnboundLocalError as e:
            # 特殊处理UnboundLocalError - 通常是agent执行异常但未返回final_answer
            error_msg = f"Agent execution incomplete: The agent encountered an error before generating a final answer. " \
                       f"This usually means the agent hit an error during execution or needs more steps. " \
                       f"Original error: {str(e)}"
            
            with self._lock:
                task_info.status = TaskStatus.FAILED
                task_info.completed_at = time.time()
                task_info.error = error_msg
                self.total_failed += 1
            
            print(f"❌ Task failed (incomplete execution): {task_id}")
            print(f"   💡 Suggestion: Try increasing max_steps or check for errors in agent execution")
            
        except Exception as e:
            # 任务执行失败
            error_msg = f"{type(e).__name__}: {str(e)}"
            
            with self._lock:
                task_info.status = TaskStatus.FAILED
                task_info.completed_at = time.time()
                task_info.error = error_msg
                self.total_failed += 1
            
            print(f"❌ Task failed: {task_id} - {error_msg}")
            traceback.print_exc()
        
        finally:
            # 恢复原来的 context
            if OTEL_AVAILABLE and token is not None:
                try:
                    context.detach(token)
                except Exception as e:
                    print(f"⚠️ Warning: Failed to detach OpenTelemetry context for task {task_id}: {e}")


class SubmitTaskTool(Tool):
    """提交任务工具"""
    
    name = "submit_task"
    description = """
    Submit a task for asynchronous execution. The task will be executed in the background.
    
    This tool supports two types of tasks:
    - 'tool': Execute a registered tool
    - 'managed_agent': Execute a managed agent
    
    Returns a task_id that can be used to check the execution status and results.
    """
    
    inputs = {
        "task_type": {
            "type": "string",
            "description": "Type of task: 'tool' or 'managed_agent'",
        },
        "target_name": {
            "type": "string", 
            "description": "Name of the tool or managed agent to execute",
        },
        "arguments": {
            "type": "object",
            "description": "Arguments to pass to the tool or managed agent",
        },
        "task_id": {
            "type": "string",
            "description": "Optional custom task ID. If not provided, a UUID will be generated.",
            "nullable": True,
        }
    }
    output_type = "string"
    
    def __init__(self, task_manager: TaskManager):
        super().__init__()
        self.task_manager = task_manager
    
    def forward(self, task_type: str, target_name: str, arguments: dict, task_id: str = None) -> str:
        """提交任务"""
        try:
            submitted_task_id = self.task_manager.submit_task(
                task_type=task_type,
                target_name=target_name,
                arguments=arguments,
                task_id=task_id
            )
            
            # 直接返回任务ID，这样可以在代码中直接使用
            return submitted_task_id
            
        except Exception as e:
            return f"Failed to submit task: {str(e)}"


class CheckTaskTool(Tool):
    """检查任务状态和结果工具"""
    
    name = "check_task"
    description = """
    Check the status and result of a previously submitted task.
    
    Returns detailed information about the task including:
    - Status (pending, running, completed, failed)
    - Result (if completed successfully)
    - Error message (if failed)
    - Timing information
    """
    
    inputs = {
        "task_id": {
            "type": "string",
            "description": "The task ID returned when the task was submitted",
        },
        "format": {
            "type": "string", 
            "description": "Output format: 'summary' (default) or 'detailed'",
            "nullable": True,
        }
    }
    output_type = "string"
    
    def __init__(self, task_manager: TaskManager):
        super().__init__()
        self.task_manager = task_manager
    
    def forward(self, task_id: str, format: str = "summary") -> str:
        """检查任务状态和结果"""
        task_info = self.task_manager.get_task_result(task_id)
        
        if not task_info:
            return f"Task not found: {task_id}"
        
        if format == "detailed":
            return self._format_detailed_result(task_info)
        else:
            return self._format_summary_result(task_info)
    
    def _format_summary_result(self, task_info: TaskInfo) -> str:
        """格式化简要结果"""
        status = task_info.status.value
        
        if task_info.status == TaskStatus.COMPLETED:
            return f"Task {task_info.task_id}: {status.upper()}\nResult: {task_info.result}"
        elif task_info.status == TaskStatus.FAILED:
            return f"Task {task_info.task_id}: {status.upper()}\nError: {task_info.error}"
        else:
            return f"Task {task_info.task_id}: {status.upper()}"
    
    def _format_detailed_result(self, task_info: TaskInfo) -> str:
        """格式化详细结果"""
        lines = [
            f"Task ID: {task_info.task_id}",
            f"Type: {task_info.task_type}",
            f"Target: {task_info.target_name}",
            f"Status: {task_info.status.value.upper()}",
            f"Created: {time.ctime(task_info.created_at)}",
        ]
        
        if task_info.started_at:
            lines.append(f"Started: {time.ctime(task_info.started_at)}")
        
        if task_info.completed_at:
            lines.append(f"Completed: {time.ctime(task_info.completed_at)}")
            duration = task_info.completed_at - task_info.created_at
            lines.append(f"Duration: {duration:.2f}s")
        
        lines.append(f"Arguments: {json.dumps(task_info.arguments, indent=2)}")
        
        if task_info.status == TaskStatus.COMPLETED:
            lines.append(f"Result: {task_info.result}")
        elif task_info.status == TaskStatus.FAILED:
            lines.append(f"Error: {task_info.error}")
        
        return "\n".join(lines)


class ListTasksTool(Tool):
    """列出任务工具"""
    
    name = "list_tasks"
    description = """
    List all submitted tasks with their status.
    Can filter by status and limit the number of results.
    """
    
    inputs = {
        "status_filter": {
            "type": "string",
            "description": "Filter by status: pending, running, completed, failed (optional)",
            "nullable": True,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of tasks to return (default: 10)",
            "nullable": True,
        }
    }
    output_type = "string"
    
    def __init__(self, task_manager: TaskManager):
        super().__init__()
        self.task_manager = task_manager
    
    def forward(self, status_filter: str = None, limit: int = 10) -> str:
        """列出任务"""
        try:
            # 解析状态过滤器
            status_enum = None
            if status_filter:
                try:
                    status_enum = TaskStatus(status_filter.lower())
                except ValueError:
                    return f"Invalid status filter: {status_filter}. Valid values: pending, running, completed, failed"
            
            # 获取任务列表
            tasks = self.task_manager.list_tasks(status_filter=status_enum)
            
            if not tasks:
                return "No tasks found."
            
            # 限制结果数量
            if limit and limit > 0:
                tasks = tasks[:limit]
            
            # 格式化输出
            lines = [f"Found {len(tasks)} task(s):"]
            lines.append("-" * 50)
            
            for task in tasks:
                duration = ""
                if task.completed_at and task.started_at:
                    duration = f" ({task.completed_at - task.started_at:.1f}s)"
                
                lines.append(
                    f"• {task.task_id[:8]}... | {task.status.value.upper()} | "
                    f"{task.task_type}:{task.target_name}{duration}"
                )
            
            # 添加统计信息
            stats = self.task_manager.get_statistics()
            lines.append("-" * 50)
            lines.append(f"Total: {stats['total_submitted']} | "
                        f"Completed: {stats['total_completed']} | "
                        f"Failed: {stats['total_failed']} | "
                        f"Pending: {stats['pending']} | "
                        f"Running: {stats['running']}")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error listing tasks: {str(e)}"


class SleepTool(Tool):
    """让Agent能够主动休眠等待的工具"""
    
    name = "sleep"
    description = """
    Sleep for a specified number of seconds. Use this when you need to wait for async tasks to complete
    or when you want to pause execution before checking task results again.
    
    This is essential for async task management - after submitting tasks, you should sleep briefly
    before checking their status to allow time for execution.
    """
    
    inputs = {
        "seconds": {
            "type": "number",
            "description": "Number of seconds to sleep (recommend not exceeding 300 seconds)"
        },
        "reason": {
            "type": "string",
            "description": "Optional reason for sleeping (for logging purposes)",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, seconds: float, reason: str = None) -> str:
        """执行休眠"""
        if seconds < 0:
            return "Error: Sleep duration cannot be negative"
            
        reason_msg = f" (Reason: {reason})" if reason else ""
        print(f"😴 Sleeping for {seconds} seconds{reason_msg}")
        
        time.sleep(seconds)
        
        return f"Slept for {seconds} seconds{reason_msg}. Ready to continue."


class WaitForTasksTool(Tool):
    """等待特定任务完成的智能工具"""
    
    name = "wait_for_tasks"
    description = """
    Wait for specific tasks to complete. This tool will periodically check task status
    and return when all specified tasks are finished (completed or failed).
    
    This tool will wait indefinitely until all tasks are done. Use this after submitting tasks
    to ensure they complete before proceeding. More intelligent than simple sleep - it actively 
    monitors task progress and returns immediately when all tasks are done.
    """
    
    inputs = {
        "task_ids": {
            "type": "array",
            "description": "List of task IDs to wait for"
        },
        "check_interval": {
            "type": "number",
            "description": "How often to check task status in seconds (default: 1)",
            "nullable": True
        }
    }
    output_type = "string"
    
    def __init__(self, task_manager: TaskManager):
        super().__init__()
        self.task_manager = task_manager
    
    def forward(self, task_ids: List[str], check_interval: float = 1) -> str:
        """等待任务完成"""
        if not task_ids:
            return "No task IDs provided"
            
        start_time = time.time()
        completed_tasks = []
        failed_tasks = []
        
        print(f"⏳ Waiting for {len(task_ids)} tasks to complete...")
        
        while True:
            all_done = True
            current_status = {}
            
            for task_id in task_ids:
                task_info = self.task_manager.get_task_result(task_id)
                if not task_info:
                    current_status[task_id] = "NOT_FOUND"
                    # 如果任务不存在，视为完成（可能是ID错误）
                    continue
                    
                status = task_info.status
                current_status[task_id] = status.value
                
                if status == TaskStatus.COMPLETED:
                    if task_id not in completed_tasks:
                        completed_tasks.append(task_id)
                elif status == TaskStatus.FAILED:
                    if task_id not in failed_tasks:
                        failed_tasks.append(task_id)
                elif status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                    all_done = False
            
            if all_done:
                elapsed = time.time() - start_time
                result = f"✅ All tasks completed in {elapsed:.1f} seconds!\n"
                result += f"Completed: {len(completed_tasks)}, Failed: {len(failed_tasks)}\n"
                
                if completed_tasks:
                    result += f"Completed tasks: {', '.join(completed_tasks[:3])}{'...' if len(completed_tasks) > 3 else ''}\n"
                if failed_tasks:
                    result += f"Failed tasks: {', '.join(failed_tasks[:3])}{'...' if len(failed_tasks) > 3 else ''}\n"
                    
                return result
            
            # 显示当前状态（每5秒显示一次，避免输出过多）
            elapsed = time.time() - start_time
            if int(elapsed) % 5 == 0 or elapsed < 5:
                status_summary = ", ".join([f"{tid[:8]}:{status}" for tid, status in current_status.items()])
                print(f"⏳ [{int(elapsed)}s] Status: {status_summary}")
            
            time.sleep(check_interval)


class GetTaskResultsTool(Tool):
    """批量获取任务结果的工具 - 直接返回字典格式"""
    
    name = "get_task_results"
    description = """
    Get results from multiple completed tasks and return them as a dictionary.
    Returns a dictionary mapping task_id -> result, making it easy to use in code.
    This is more efficient than checking tasks individually when you need results from several tasks.
    """
    
    inputs = {
        "task_ids": {
            "type": "array",
            "description": "List of task IDs to get results for"
        },
        "include_failed": {
            "type": "boolean",
            "description": "Whether to include failed tasks in results (default: true)",
            "nullable": True
        }
    }
    output_type = "object"
    
    def __init__(self, task_manager: TaskManager):
        super().__init__()
        self.task_manager = task_manager
    
    def forward(self, task_ids: list, include_failed: bool = True) -> dict:
        """获取多个任务的结果，直接返回字典"""
        if not task_ids:
            return {}
            
        results_dict = {}
        
        for task_id in task_ids:
            task_info = self.task_manager.get_task_result(task_id)
            
            if not task_info:
                results_dict[task_id] = f"Task {task_id}: NOT FOUND"
                continue
                
            if task_info.status == TaskStatus.COMPLETED:
                results_dict[task_id] = task_info.result
                
            elif task_info.status == TaskStatus.FAILED and include_failed:
                results_dict[task_id] = f"FAILED - {task_info.error}"
                
            elif task_info.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                results_dict[task_id] = f"{task_info.status.value.upper()}"
        
        return results_dict

class AsyncAgent:
    """
    智能异步Agent - 包装CodeAgent，提供智能的异步任务管理能力
    专注于任务拆解、分发和协调
    """
    
    def __init__(self, base_agent, max_workers: int = 3):
        """
        初始化智能异步Agent
        
        Args:
            base_agent: 基础的CodeAgent实例
            max_workers: 最大工作线程数
        """
        self.base_agent = base_agent
        # 每个 AsyncAgent 有自己的 TaskManager 实例
        self.task_manager = TaskManager(max_workers=max_workers)
        
        # 注册基础agent的工具和managed agents
        self.task_manager.register_tools(base_agent.tools)
        if hasattr(base_agent, 'managed_agents'):
            self.task_manager.register_managed_agents(base_agent.managed_agents)
        
        # 添加智能异步工具（传入 task_manager 实例）
        async_tools = {
            "submit_task": SubmitTaskTool(self.task_manager),
            "check_task": CheckTaskTool(self.task_manager),
            "list_tasks": ListTasksTool(self.task_manager),
            "sleep": SleepTool(),
            "wait_for_tasks": WaitForTasksTool(self.task_manager),
            "get_task_results": GetTaskResultsTool(self.task_manager),
        }
        
        # 将异步工具添加到基础agent
        self.base_agent.tools.update(async_tools)
        
        # 启动任务管理器
        self.task_manager.start()
        
        # 更新系统提示，指导agent使用异步功能
        self._enhance_system_prompt()
        
        # 打印初始化信息
        print(f"🧠 AsyncAgent initialized with {len(self.base_agent.tools)} tools")
        print(f"⚡ Max concurrent tasks (max_workers): {self.task_manager.max_workers}")
        print(f"📋 Available async tools: {', '.join(async_tools.keys())}")
        
        # 显示可用资源
        available_tools = [t for t in self.task_manager.tools.keys() if t not in async_tools]
        available_agents = list(self.task_manager.managed_agents.keys())
        
        if available_tools:
            print(f"🛠️  Available Tools (task_type='tool'): {', '.join(available_tools)}")
        if available_agents:
            print(f"🤖 Available Managed Agents (task_type='managed_agent'): {', '.join(available_agents)}")
    
    def _enhance_system_prompt(self):
        """增强系统提示，指导agent进行异步任务管理"""
        
        # 获取可用的工具和agents列表
        available_tools = list(self.task_manager.tools.keys())
        available_agents = list(self.task_manager.managed_agents.keys())
        
        # 构建资源清单
        resources_info = f"""
### 📦 可用资源清单

**系统配置**:
- 最大并发任务数 (max_workers): {self.task_manager.max_workers}
  - 这是系统同时执行的最大任务数量
  - 超过此数量的任务会排队等待
  - 建议根据此数量合理规划并行任务

**可用的 Tools (使用 task_type="tool")**:
{chr(10).join(f'  - {tool}' for tool in available_tools) if available_tools else '  (无)'}

**可用的 Managed Agents (使用 task_type="managed_agent")**:
{chr(10).join(f'  - {agent}' for agent in available_agents) if available_agents else '  (无)'}

⚠️ **重要**: 
- 使用 submit_task 时，必须正确指定 task_type：
  - 对于上面列出的 Tools，使用 task_type="tool"
  - 对于上面列出的 Managed Agents，使用 task_type="managed_agent"
- 错误的 task_type 会导致任务提交失败
"""
        
        async_guidance = f"""

## 异步任务管理指南

你现在具备了强大的异步任务管理能力。以下是使用指南：

{resources_info}

### 🚀 异步工作流程
1. **任务分析**: 分析复杂任务，识别可以并行执行的子任务
2. **任务分发**: 使用submit_task工具将子任务提交到异步队列
3. **智能等待**: 使用wait_for_tasks等待任务完成（无超时限制，会等待所有任务完成）
4. **结果收集**: 使用get_task_results批量获取结果
5. **结果整合**: 将异步结果整合为最终答案

### 🛠️ 可用的异步工具
- `submit_task`: 提交任务到异步队列 - 直接返回任务ID
  - 参数: task_type (必须是 "tool" 或 "managed_agent")
  - 参数: target_name (工具名或agent名，见上方资源清单)
  - 参数: arguments (传递给工具/agent的参数)
- `wait_for_tasks`: 智能等待指定任务完成（会一直等到所有任务完成）
- `get_task_results`: 批量获取任务结果（直接返回字典）
- `check_task`: 检查单个任务状态
- `list_tasks`: 列出所有任务

### 💡 最佳实践
1. **合理规划并发**: 系统最大支持 {self.task_manager.max_workers} 个并发任务
   - 一次提交大约 {self.task_manager.max_workers} 个任务最合适
   - 提交更多任务会排队，但不会失败
   - 对于大批量任务，考虑分批提交
2. **正确使用 task_type**: 根据上方资源清单选择正确的 task_type
3. **识别并行机会**: 寻找可以同时执行的独立任务
4. **等待任务完成**: 提交任务后，使用 wait_for_tasks 等待（会等到所有任务完成）
5. **批量操作**: 使用 get_task_results 批量获取结果，提高效率
6. **错误处理**: 检查任务是否失败，并有备用方案

### 📝 示例异步模式

```python
# 1. 并行使用工具（task_type="tool"）- 适合快速任务
# 当前系统支持 {self.task_manager.max_workers} 个并发任务
task1_id = submit_task("tool", "data_processor", {{"dataset": "A"}})
task2_id = submit_task("tool", "data_processor", {{"dataset": "B"}})
task3_id = submit_task("tool", "data_processor", {{"dataset": "C"}})
wait_for_tasks([task1_id, task2_id, task3_id])  # 会等待所有任务完成

# 使用get_task_results直接获取字典结果
results_dict = get_task_results([task1_id, task2_id, task3_id])
result_a = results_dict[task1_id]
result_b = results_dict[task2_id]
result_c = results_dict[task3_id]

# 2. 并行使用代理（task_type="managed_agent"）
agent_task = submit_task("managed_agent", "filesystem_agent", {{
    "task": "分析系统日志",
    "additional_args": {{}}
}})
wait_for_tasks([agent_task])
agent_results = get_task_results([agent_task])

# 3. 混合使用工具和代理
tool_task = submit_task("tool", "calculation", {{"x": 10}})
agent_task = submit_task("managed_agent", "analyst_agent", {{"task": "分析数据"}})
wait_for_tasks([tool_task, agent_task])
final_results = get_task_results([tool_task, agent_task])

# 4. 大批量任务分批处理（如果任务数 > max_workers）
all_datasets = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
batch_size = {self.task_manager.max_workers}  # 根据并发数分批

for i in range(0, len(all_datasets), batch_size):
    batch = all_datasets[i:i+batch_size]
    task_ids = [submit_task("tool", "process", {{"data": d}}) for d in batch]
    wait_for_tasks(task_ids)
    results = get_task_results(task_ids)
    # 处理这批结果...
```

现在，你可以智能地分解复杂任务，并行执行，大大提高处理效率！
"""
        
        # 将异步指南添加到系统提示中
        if hasattr(self.base_agent, 'instructions'):
            if self.base_agent.instructions:
                self.base_agent.instructions += async_guidance
            else:
                self.base_agent.instructions = async_guidance.strip()
        else:
            # 如果没有instructions属性，尝试修改prompt_templates
            if hasattr(self.base_agent, 'prompt_templates') and 'system_prompt' in self.base_agent.prompt_templates:
                original_prompt = self.base_agent.prompt_templates['system_prompt']
                self.base_agent.prompt_templates['system_prompt'] = original_prompt + async_guidance
    
    def __getattr__(self, name):
        """代理所有其他属性和方法到基础agent"""
        return getattr(self.base_agent, name)
    
    def run_with_async_guidance(self, task: str, **kwargs) -> str:
        """
        运行任务，并提供异步处理的额外指导
        """
        # 在任务前添加异步处理提示
        enhanced_task = f"""
{task}

---
💡 异步处理提示：
- 如果这个任务可以拆分为多个独立的子任务，考虑使用submit_task并行执行
- 提交任务后，使用wait_for_tasks等待完成，而不是立即检查
- 对于耗时操作，优先考虑异步处理
- 使用get_task_results批量获取多个任务的结果（直接返回字典）：
  ```python
  # 直接获取字典结果
  results_dict = get_task_results(task_ids, include_failed=True)
  # 直接通过任务ID访问结果
  sales_analysis = results_dict[sales_task_id]
  customer_analysis = results_dict[customer_task_id]
  market_analysis = results_dict[market_task_id]
  ```
"""
        
        return self.base_agent.run(enhanced_task, **kwargs)
    
    def shutdown(self):
        """关闭异步系统"""
        self.task_manager.stop()
        print("🛑 AsyncAgent shutdown")


def create_async_agent(tools: List[Tool] = None, managed_agents: List = None, 
                                  model=None, max_workers: int = 3, **kwargs):
    """
    创建智能异步CodeAgent的便捷函数
    
    Args:
        tools: 工具列表
        managed_agents: 受管理的agent列表
        model: 语言模型
        max_workers: 最大工作线程数
        **kwargs: 传递给CodeAgent的其他参数
        
    Returns:
        AsyncAgent实例
    """
    from smolagents import CodeAgent
    
    base_agent = CodeAgent(
        tools=tools or [],
        model=model,
        managed_agents=managed_agents or [],
        additional_authorized_imports=['*'],
        **kwargs
    )
    
    return AsyncAgent(base_agent, max_workers=max_workers)
