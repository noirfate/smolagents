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


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 待执行
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 执行失败
    CANCELLED = "cancelled"  # 已取消


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
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['status'] = self.status.value
        return data


class TaskManager:
    """任务管理器 - 管理任务队列和执行结果"""
    
    def __init__(self, max_workers: int = 3):
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
        """注册可用的managed agents"""
        with self._lock:
            self.managed_agents.update(managed_agents)
    
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
        
        # 验证目标是否存在
        if task_type == "tool" and target_name not in self.tools:
            raise ValueError(f"Tool '{target_name}' not found")
        elif task_type == "managed_agent" and target_name not in self.managed_agents:
            raise ValueError(f"Managed agent '{target_name}' not found")
        
        task_info = TaskInfo(
            task_id=task_id,
            task_type=task_type,
            target_name=target_name,
            arguments=arguments,
            status=TaskStatus.PENDING,
            created_at=time.time()
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
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务（仅对未开始的任务有效）"""
        with self._lock:
            task_info = self.task_results.get(task_id)
            if task_info and task_info.status == TaskStatus.PENDING:
                task_info.status = TaskStatus.CANCELLED
                return True
            return False
    
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
                
                # 检查任务是否被取消
                if task_info.status == TaskStatus.CANCELLED:
                    continue
                
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
                agent = self.managed_agents[task_info.target_name]
                if isinstance(task_info.arguments, dict):
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


# 全局任务管理器实例
global_task_manager = TaskManager()


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
    
    def forward(self, task_type: str, target_name: str, arguments: dict, task_id: str = None) -> str:
        """提交任务"""
        try:
            submitted_task_id = global_task_manager.submit_task(
                task_type=task_type,
                target_name=target_name,
                arguments=arguments,
                task_id=task_id
            )
            
            return f"Task submitted successfully! Task ID: {submitted_task_id}"
            
        except Exception as e:
            return f"Failed to submit task: {str(e)}"


class CheckTaskTool(Tool):
    """检查任务状态和结果工具"""
    
    name = "check_task"
    description = """
    Check the status and result of a previously submitted task.
    
    Returns detailed information about the task including:
    - Status (pending, running, completed, failed, cancelled)
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
    
    def forward(self, task_id: str, format: str = "summary") -> str:
        """检查任务状态和结果"""
        task_info = global_task_manager.get_task_result(task_id)
        
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
            "description": "Filter by status: pending, running, completed, failed, cancelled (optional)",
            "nullable": True,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of tasks to return (default: 10)",
            "nullable": True,
        }
    }
    output_type = "string"
    
    def forward(self, status_filter: str = None, limit: int = 10) -> str:
        """列出任务"""
        try:
            # 解析状态过滤器
            status_enum = None
            if status_filter:
                try:
                    status_enum = TaskStatus(status_filter.lower())
                except ValueError:
                    return f"Invalid status filter: {status_filter}. Valid values: pending, running, completed, failed, cancelled"
            
            # 获取任务列表
            tasks = global_task_manager.list_tasks(status_filter=status_enum)
            
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
            stats = global_task_manager.get_statistics()
            lines.append("-" * 50)
            lines.append(f"Total: {stats['total_submitted']} | "
                        f"Completed: {stats['total_completed']} | "
                        f"Failed: {stats['total_failed']} | "
                        f"Pending: {stats['pending']} | "
                        f"Running: {stats['running']}")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error listing tasks: {str(e)}"


class AsyncToolCallingAgent:
    """支持异步任务执行的ToolCallingAgent包装器"""
    
    def __init__(self, base_agent, max_workers: int = 3):
        """
        初始化异步Agent
        
        Args:
            base_agent: 基础的ToolCallingAgent实例
            max_workers: 最大工作线程数
        """
        self.base_agent = base_agent
        self.task_manager = global_task_manager
        
        # 注册基础agent的工具和managed agents
        self.task_manager.register_tools(base_agent.tools)
        if hasattr(base_agent, 'managed_agents'):
            self.task_manager.register_managed_agents(base_agent.managed_agents)
        
        # 添加异步任务工具到基础agent
        async_tools = {
            "submit_task": SubmitTaskTool(),
            "check_task": CheckTaskTool(), 
            "list_tasks": ListTasksTool(),
        }
        
        self.base_agent.tools.update(async_tools)
        
        # 启动任务管理器
        self.task_manager.start()
        
        print(f"🚀 AsyncToolCallingAgent initialized with {len(self.base_agent.tools)} tools")
    
    def __getattr__(self, name):
        """代理所有其他属性和方法到基础agent"""
        return getattr(self.base_agent, name)
    
    def shutdown(self):
        """关闭异步系统"""
        self.task_manager.stop()
        print("🛑 AsyncToolCallingAgent shutdown")

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
            "description": "Number of seconds to sleep (can be decimal, e.g., 1.5 for 1.5 seconds)"
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
        
        if seconds > 60:  # 限制最大休眠时间，避免长时间卡住
            seconds = 60
            
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
    
    More intelligent than simple sleep - it actively monitors task progress.
    """
    
    inputs = {
        "task_ids": {
            "type": "array",
            "description": "List of task IDs to wait for"
        },
        "max_wait_time": {
            "type": "number", 
            "description": "Maximum time to wait in seconds (default: 30)",
            "nullable": True
        },
        "check_interval": {
            "type": "number",
            "description": "How often to check task status in seconds (default: 1)",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, task_ids: List[str], max_wait_time: float = 30, check_interval: float = 1) -> str:
        """等待任务完成"""
        if not task_ids:
            return "No task IDs provided"
            
        start_time = time.time()
        completed_tasks = []
        failed_tasks = []
        
        print(f"⏳ Waiting for {len(task_ids)} tasks to complete...")
        
        while time.time() - start_time < max_wait_time:
            all_done = True
            current_status = {}
            
            for task_id in task_ids:
                task_info = global_task_manager.get_task_result(task_id)
                if not task_info:
                    current_status[task_id] = "NOT_FOUND"
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
                result = f"All tasks completed in {elapsed:.1f} seconds!\n"
                result += f"Completed: {len(completed_tasks)}, Failed: {len(failed_tasks)}\n"
                
                if completed_tasks:
                    result += f"Completed tasks: {', '.join(completed_tasks[:3])}{'...' if len(completed_tasks) > 3 else ''}\n"
                if failed_tasks:
                    result += f"Failed tasks: {', '.join(failed_tasks[:3])}{'...' if len(failed_tasks) > 3 else ''}\n"
                    
                return result
            
            # 显示当前状态
            status_summary = ", ".join([f"{tid[:8]}:{status}" for tid, status in current_status.items()])
            print(f"⏳ Status: {status_summary}")
            
            time.sleep(check_interval)
        
        # 超时
        elapsed = time.time() - start_time
        return f"Timeout after {elapsed:.1f} seconds. Some tasks may still be running. Completed: {len(completed_tasks)}, Failed: {len(failed_tasks)}"


class GetTaskResultsTool(Tool):
    """批量获取任务结果的工具"""
    
    name = "get_task_results"
    description = """
    Get results from multiple completed tasks at once. 
    This is more efficient than checking tasks individually when you need results from several tasks.
    Returns a formatted string with task results and embedded JSON dictionary.
    Use parse_task_results() to extract the results dictionary for easy access to individual task results.
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
    output_type = "string"
    
    def forward(self, task_ids: List[str], include_failed: bool = True) -> str:
        """获取多个任务的结果，返回包含结果字典的特殊格式字符串"""
        if not task_ids:
            return "No task IDs provided\n\n# RESULTS_DICT_JSON: {}"
            
        results = []
        completed_count = 0
        failed_count = 0
        results_dict = {}
        
        for task_id in task_ids:
            task_info = global_task_manager.get_task_result(task_id)
            
            if not task_info:
                results.append(f"❌ Task {task_id}: NOT FOUND")
                results_dict[task_id] = f"Task {task_id}: NOT FOUND"
                continue
                
            if task_info.status == TaskStatus.COMPLETED:
                completed_count += 1
                results.append(f"✅ Task {task_id}: {task_info.result}")
                results_dict[task_id] = task_info.result
                
            elif task_info.status == TaskStatus.FAILED and include_failed:
                failed_count += 1
                results.append(f"❌ Task {task_id}: FAILED - {task_info.error}")
                results_dict[task_id] = f"FAILED - {task_info.error}"
                
            elif task_info.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                results.append(f"⏳ Task {task_id}: {task_info.status.value.upper()}")
                results_dict[task_id] = f"{task_info.status.value.upper()}"
        
        summary = f"Results Summary: {completed_count} completed, {failed_count} failed\n"
        summary += "="*50 + "\n"
        summary += "\n".join(results)
        
        # 添加特殊的结果字典标记，用于解析
        summary += f"\n\n# RESULTS_DICT_JSON: {json.dumps(results_dict)}"
        
        return summary

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
        self.task_manager = global_task_manager
        
        # 注册基础agent的工具和managed agents
        self.task_manager.register_tools(base_agent.tools)
        if hasattr(base_agent, 'managed_agents'):
            self.task_manager.register_managed_agents(base_agent.managed_agents)
        
        # 添加智能异步工具
        async_tools = {
            "submit_task": SubmitTaskTool(),
            "check_task": CheckTaskTool(),
            "list_tasks": ListTasksTool(),
            "sleep": SleepTool(),
            "wait_for_tasks": WaitForTasksTool(),
            "get_task_results": GetTaskResultsTool(),
        }
        
        # 将异步工具添加到基础agent
        self.base_agent.tools.update(async_tools)
        
        # 启动任务管理器
        self.task_manager.start()
        
        # 更新系统提示，指导agent使用异步功能
        self._enhance_system_prompt()
        
        print(f"🧠 SmartAsyncAgent initialized with {len(self.base_agent.tools)} tools")
        print(f"📋 Available async tools: {', '.join(async_tools.keys())}")
    
    def _enhance_system_prompt(self):
        """增强系统提示，指导agent进行异步任务管理"""
        
        async_guidance = """

## 异步任务管理指南

你现在具备了强大的异步任务管理能力。以下是使用指南：

### 🚀 异步工作流程
1. **任务分析**: 分析复杂任务，识别可以并行执行的子任务
2. **任务分发**: 使用submit_task工具将子任务提交到异步队列
3. **智能等待**: 使用wait_for_tasks或sleep工具等待任务完成
4. **结果收集**: 使用get_task_results批量获取结果
5. **结果整合**: 将异步结果整合为最终答案

### 🛠️ 可用的异步工具
- `submit_task`: 提交任务到异步队列（支持tool和managed_agent）
- `wait_for_tasks`: 智能等待指定任务完成
- `sleep`: 简单休眠等待
- `get_task_results`: 批量获取任务结果
- `check_task`: 检查单个任务状态
- `list_tasks`: 列出所有任务

### 💡 最佳实践
1. **识别并行机会**: 寻找可以同时执行的独立任务
2. **合理等待**: 提交任务后，使用wait_for_tasks而不是盲目sleep
3. **错误处理**: 检查任务是否失败，并有备用方案
4. **批量操作**: 使用get_task_results批量获取结果，提高效率
5. **进度监控**: 定期检查长时间运行任务的状态

### 📝 示例异步模式

```python
# 1. 并行数据处理
task1_id = submit_task("tool", "data_processor", {"dataset": "A"})
task2_id = submit_task("tool", "data_processor", {"dataset": "B"})
wait_for_tasks([task1_id, task2_id], max_wait_time=30)
# 定义解析函数
import json, re
def parse_task_results(results_string):
    match = re.search(r'# RESULTS_DICT_JSON: (.+)', results_string)
    return json.loads(match.group(1)) if match else {}

results_str = get_task_results([task1_id, task2_id])
results_dict = parse_task_results(results_str)

# 2. 流水线处理
step1_id = submit_task("tool", "preprocess", {"data": input_data})
wait_for_tasks([step1_id])
step1_results_str = get_task_results([step1_id])
step1_results_dict = parse_task_results(step1_results_str)
step2_id = submit_task("tool", "analyze", {"data": step1_results_dict[step1_id]})

# 3. 混合任务类型
tool_task = submit_task("tool", "calculation", {...})
agent_task = submit_task("managed_agent", "analyst", {...})
wait_for_tasks([tool_task, agent_task])
```

### ⚠️ 重要提醒
- 总是在提交任务后适当等待，不要立即检查结果
- 使用wait_for_tasks比简单sleep更智能
- 长时间任务要设置合理的超时时间
- 处理任务失败的情况，提供备用方案

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
- 使用get_task_results批量获取多个任务的结果，然后定义解析函数来提取结果字典：
  ```python
  # 定义解析函数
  import json, re
  def parse_task_results(results_string):
      match = re.search(r'# RESULTS_DICT_JSON: (.+)', results_string)
      return json.loads(match.group(1)) if match else {{}}
  
  results_str = get_task_results(task_ids, include_failed=True)
  results_dict = parse_task_results(results_str)
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
        print("🛑 SmartAsyncAgent shutdown")


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
