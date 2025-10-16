# 智能异步Agent系统使用指南

## 🧠 核心理念

让 **CodeAgent 作为主控制器**，自主地进行任务拆解、分发和协调，而不是硬编码任务。Agent 会：

1. **智能分析**：分析复杂任务，识别可并行执行的子任务
2. **动态分发**：根据任务性质选择合适的工具或managed agents
3. **自主等待**：使用sleep和wait_for_tasks工具智能等待异步任务完成
4. **结果整合**：收集并整合异步任务结果

## 🛠️ 系统组件

### 核心工具集
- `submit_task` - 提交异步任务（直接返回任务ID）
- `wait_for_tasks` - 智能等待指定任务完成
- `sleep` - 简单休眠等待
- `get_task_results` - 批量获取任务结果（直接返回字典）
- `check_task` - 检查单个任务状态
- `list_tasks` - 列出所有任务

### AsyncAgent
包装CodeAgent，提供：
- 自动的系统提示增强
- 智能异步工具集成
- 任务管理器生命周期管理
- 智能任务拆解和协调能力

## 📖 使用方法

### 基础用法

```python
import os
from dotenv import load_dotenv
from async_task_system import create_async_agent
from smolagents import LiteLLMModel

# 加载环境变量
load_dotenv(override=True)

# 创建智能异步CodeAgent
model = LiteLLMModel(
    model_id="litellm_proxy/gpt-3.5-turbo",
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
    max_completion_tokens=8192
)

async_agent = create_async_agent(
    tools=[your_tools],
    managed_agents=[your_agents],
    model=model,
    max_workers=3
)

# 让Agent自主处理复杂任务
result = async_agent.run_with_async_guidance("""
我需要分析5个数据集，每个分析需要3-5秒。
请设计一个高效的并行处理方案。
""")

async_agent.shutdown()
```

### Agent的智能行为

Agent现在会自动：

1. **识别并行机会**
   ```
   用户：分析3个数据集
   Agent：我发现这3个分析可以并行执行，让我提交3个异步任务...
   ```

2. **智能等待**
   ```python
   # Agent会这样做：
   task1 = submit_task("tool", "analyze_dataset", {...})  # 直接返回任务ID
   task2 = submit_task("tool", "analyze_dataset", {...})  
   task3 = submit_task("tool", "analyze_dataset", {...})
   
   wait_for_tasks([task1, task2, task3], max_wait_time=30)
   results = get_task_results([task1, task2, task3])  # 直接返回字典
   ```

3. **错误处理和重试**
   ```
   Agent：检测到任务失败，让我检查错误原因并重新提交...
   ```

## 🎯 典型使用场景

### 场景1：批量数据处理
```python
task = """
我有10个数据文件需要处理，每个文件的处理包括：
1. 数据清洗
2. 统计分析  
3. 生成可视化图表

请优化处理流程，减少总体时间。
"""

result = async_agent.run_with_async_guidance(task)
```

**Agent会自动**：
- 识别出30个子任务（10文件 × 3步骤）
- 分析依赖关系（清洗→分析→可视化）
- 设计流水线：先并行清洗，再并行分析，最后并行生成图表

### 场景2：多源数据整合
```python
task = """
我需要从以下数据源获取数据并整合：
- 数据库A：用户信息
- 数据库B：交易记录
- API C：实时市场数据
- 文件D：历史数据

请高效地获取并整合这些数据。
"""
```

**Agent会自动**：
- 并行查询所有数据源
- 使用wait_for_tasks等待所有数据获取完成
- 整合数据并生成最终报告

### 场景3：复合分析任务
```python
task = """
对我们的电商平台进行全面分析：
1. 用户行为分析（需要机器学习专家）
2. 销售趋势分析
3. 库存优化建议
4. 竞争对手分析
5. 综合战略报告

每个分析都比较耗时，请优化执行。
"""
```

**Agent会自动**：
- 识别独立任务（1-4可并行）
- 提交给合适的工具/agents
- 等待所有分析完成
- 整合结果生成综合报告

## 🔧 高级配置

### 自定义系统提示
```python
async_agent = create_async_agent(
    tools=tools,
    model=model,
    instructions="""
你是一个专业的项目经理，擅长任务分解和并行处理。
总是优先考虑效率和并行执行的可能性。
"""
)
```

### 调整并发度
```python
# 高并发场景
async_agent = create_async_agent(
    max_workers=8,  # 更多工作线程
    model=model
)
```

### 监控和调试
```python
# 获取实时统计
stats = async_agent.task_manager.get_statistics()
print(f"Running tasks: {stats['running']}")

# 查看所有任务
result = async_agent.run("请使用list_tasks工具显示所有任务状态")
```

## 💡 Agent行为模式

### 典型的Agent工作流程

1. **任务分析阶段**
   ```
   Agent: 分析您的需求，我发现可以将此任务分解为以下子任务...
   ```

2. **并行执行阶段**
   ```python
   # Agent会执行类似的代码：
   task_ids = []
   for subtask in subtasks:
       task_id = submit_task(subtask.type, subtask.name, subtask.args)
       task_ids.append(task_id)
   ```

3. **智能等待阶段**
   ```python
   # Agent选择合适的等待策略：
   wait_for_tasks(task_ids, max_wait_time=60)
   # 或者
   sleep(5, reason="等待数据处理任务完成")
   ```

4. **结果收集阶段**
   ```python
   results = get_task_results(task_ids)  # 直接返回字典 {task_id: result}
   result1 = results[task_ids[0]]  # 直接使用结果
   ```

5. **整合输出阶段**
   ```
   Agent: 基于以上异步任务的结果，我为您整合了最终报告...
   ```

## ⚠️ 最佳实践

1. **明确任务边界**：清楚描述你的需求，让Agent更好地识别并行机会

2. **合理设置超时**：对于长时间运行的任务，设置合理的max_wait_time

3. **监控资源使用**：根据系统资源调整max_workers

4. **错误恢复**：Agent会自动处理任务失败，但复杂场景可能需要人工干预

5. **渐进式复杂度**：从简单任务开始，逐步尝试更复杂的并行场景

## 🚀 示例对话

```
用户：我需要分析公司的季度业绩，包括销售、市场、运营三个维度的数据

Agent：我来为您设计一个高效的分析方案：

1. 首先，我识别到这三个维度的分析可以并行执行
2. 让我提交三个异步任务...

# 提交任务（直接获得任务ID）
sales_task = submit_task("tool", "analyze_sales", {"quarter": "Q1"})
market_task = submit_task("tool", "analyze_market", {"quarter": "Q1"}) 
ops_task = submit_task("tool", "analyze_operations", {"quarter": "Q1"})

# 智能等待所有任务完成
wait_for_tasks([sales_task, market_task, ops_task], max_wait_time=60)

# 直接获取结果字典
results = get_task_results([sales_task, market_task, ops_task])

所有分析任务已完成！基于以下结果：
- 销售分析：{results[sales_task]}
- 市场分析：{results[market_task]}
- 运营分析：{results[ops_task]}

让我整合这些结果为您生成综合的季度业绩报告...
```

这就是智能异步Agent的强大之处 - **Agent成为了任务协调者**，自动处理复杂的并行任务流程！

## 🔍 OpenTelemetry 追踪支持

### 问题：异步任务中 Trace 断裂

在多线程环境中执行异步任务时，OpenTelemetry 的 trace context 默认不会自动传递到新线程，导致：
- Phoenix/其他监控平台中只能看到部分 trace
- 主 agent 和异步任务的 trace 不连贯
- 难以完整追踪整个任务流程

### 解决方案：自动 Context 传递

系统已自动集成 OpenTelemetry context 传递：

1. **提交任务时捕获 context**：
   - 在 `submit_task` 时自动捕获当前的 OpenTelemetry context
   - 将 context 存储在 `TaskInfo` 中

2. **执行任务时恢复 context**：
   - 在 `_execute_task` 中恢复父任务的 context
   - 异步任务的 trace 会正确关联到主任务
   - 执行完成后自动清理 context

3. **完全透明**：
   - 无需修改现有代码
   - 自动检测 OpenTelemetry 是否可用
   - 即使没有安装 OpenTelemetry 也能正常工作

### 使用示例

```python
# 启用监控（在创建 agent 之前）
from phoenix.otel import register
from openinference.instrumentation.smolagents import SmolagentsInstrumentor

register(
   project_name=project_name,
   endpoint="http://localhost:6006/v1/traces",
   auto_instrument=True,
   set_global_tracer_provider=False
)
SmolagentsInstrumentor().instrument()

# 正常使用异步 agent
async_agent = create_async_agent(tools=tools, model=model)
result = async_agent.run_with_async_guidance("你的任务")

# 在 Phoenix UI 中查看完整、连贯的 trace
# http://localhost:6006
```

### 效果

✅ **完整的 Trace 链**：从主 agent 到所有异步子任务
✅ **正确的父子关系**：清晰展示任务依赖和调用关系
✅ **连贯的时间线**：准确显示并行执行的时序关系
✅ **完整的 Span 信息**：LLM 调用、工具执行、错误信息全部可见

### 技术细节

- 使用 `opentelemetry.context` 进行 context 传递
- 在线程边界显式传递和恢复 context
- 使用 `attach/detach` 确保 context 正确隔离
- 失败时有 fallback，不影响任务执行