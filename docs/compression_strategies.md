# 记忆压缩策略说明

## 概述

`MemoryManager` 提供了两种记忆压缩策略，可通过 `aggressive_compression` 参数配置：

- **激进策略（Aggressive）**：默认，更节省 token
- **保守策略（Conservative）**：保留更多上下文

## 策略对比

### 激进策略（aggressive_compression=True，默认）

**压缩规则**：
- 压缩当前（最后一个）planning step 之前的**所有内容**
- 只保留：当前 plan + 后续 action 步骤

**示例**：
```
执行历史：
  TaskStep
  ActionStep 1
  ActionStep 2
  PlanningStep 1  ← 旧 plan
  ActionStep 3
  ActionStep 4
  PlanningStep 2  ← 当前 plan (split point)
  ActionStep 5    ← 最新执行

压缩后保留：
  [压缩摘要: TaskStep, Action 1-4, Plan 1]
  PlanningStep 2 (包含历史代码摘要)
  ActionStep 5
```

**优势**：
- ✅ 大幅节省 token（最多可节省 50-70%）
- ✅ 当前 plan 中已包含历史代码执行摘要
- ✅ 模型可通过工具（`search_history_steps`、`get_step_content`）查看详细历史
- ✅ 完整历史保存在文件中，不会丢失

**适用场景**：
- 长时间运行的任务（50+ 步骤）
- 需要严格控制 token 使用
- 任务主要依赖代码执行（CodeAgent）

---

### 保守策略（aggressive_compression=False）

**压缩规则**：
- 压缩倒数第二个 planning step 之前的内容
- 保留：最近一次完整的 {action, plan} 周期

**示例**：
```
执行历史：
  TaskStep
  ActionStep 1
  ActionStep 2
  PlanningStep 1  ← 倒数第二个 plan (split point)
  ActionStep 3
  ActionStep 4
  PlanningStep 2  ← 当前 plan
  ActionStep 5    ← 最新执行

压缩后保留：
  [压缩摘要: TaskStep, Action 1-2]
  PlanningStep 1
  ActionStep 3
  ActionStep 4
  PlanningStep 2 (包含历史代码摘要)
  ActionStep 5
```

**优势**：
- ✅ 保留更多最近的执行细节
- ✅ 模型可以看到上一个 plan 及其执行结果
- ✅ 更安全，信息丢失风险更低

**适用场景**：
- 中短期任务（<50 步骤）
- 需要保持详细上下文的任务
- 调试和问题诊断

---

## 使用方法

### 1. 使用激进策略（默认）

```python
from smolagents import MemoryCompressedCodeAgent, HfApiModel

model = HfApiModel(model_id="Qwen/Qwen2.5-Coder-32B-Instruct")

agent = MemoryCompressedCodeAgent(
    tools=[],
    model=model,
    planning_interval=3,
    memory_dir="./memory",
    aggressive_compression=True  # 默认值，可省略
)
```

### 2. 使用保守策略

```python
agent = MemoryCompressedCodeAgent(
    tools=[],
    model=model,
    planning_interval=3,
    memory_dir="./memory",
    aggressive_compression=False  # 使用保守策略
)
```

---

## 技术细节

### 实现方法

**激进策略**：`get_compression_split_point()`
```python
def get_compression_split_point(self, memory_steps):
    planning_indices = self.get_planning_step_indices(memory_steps)
    if len(planning_indices) < 1:
        return -1
    
    # 使用最后一个 planning step 作为分割点
    last_plan_idx = planning_indices[-1]
    return last_plan_idx
```

**保守策略**：`get_compression_split_point_conservative()`
```python
def get_compression_split_point_conservative(self, memory_steps):
    planning_indices = self.get_planning_step_indices(memory_steps)
    if len(planning_indices) < 2:
        return -1
    
    # 使用倒数第二个 planning step 作为分割点
    second_last_plan_idx = planning_indices[-2]
    return second_last_plan_idx
```

### 配置切换

在 `MemoryManager` 初始化时：
```python
class MemoryManager:
    def __init__(self, agent, memory_dir=".", aggressive_compression=True):
        self.aggressive_compression = aggressive_compression
```

在压缩时自动选择策略：
```python
def write_memory_to_messages_with_compression(self, summary_mode=False):
    if self.aggressive_compression:
        split_point = self.get_compression_split_point(memory_steps)
    else:
        split_point = self.get_compression_split_point_conservative(memory_steps)
```

---

## 性能对比

| 指标 | 激进策略 | 保守策略 |
|------|---------|---------|
| Token 节省 | 50-70% | 30-40% |
| 压缩触发 | 第1次 plan 后 | 第2次 plan 后 |
| 保留步骤数 | 最少 | 中等 |
| 信息完整度 | 摘要+工具 | 详细 |
| 适用任务长度 | >50 步 | <50 步 |

---

## 历史代码摘要限制

为避免 plan 文本过长，历史代码摘要有以下限制：

- **数量限制**：只显示最近 `planning_interval × 2` 个代码执行步骤
- **默认值**：如果未设置 `planning_interval`，默认最多显示 16 个代码步骤
- **示例**：如果 `planning_interval=8`，则最多显示 16 个最近的代码步骤
- **更早的代码**：模型可通过 `search_history_steps` 工具查看

**示例输出**：
```
**历史代码执行摘要** (用于变量复用):

显示最近 16 个代码执行步骤（共 35 个）。如需查看更早的代码，可使用 search_history_steps 工具。

你在之前的步骤中已经执行了以下代码，这些执行产生的变量仍然可用：
...
```

---

## 注意事项

### 激进策略注意事项

1. **历史代码摘要**：确保在 planning 时正确追加历史代码（由 `MemoryCompressedCodeAgent._generate_planning_step` 处理）
2. **摘要数量限制**：只显示最近 `planning_interval × 2` 个代码步骤
3. **工具可用性**：模型需要知道可以使用 `search_history_steps` 和 `get_step_content` 查看历史
4. **文件可访问性**：历史文件路径会在压缩摘要中提示

### 保守策略注意事项

1. **Token 使用**：长任务可能导致 token 超限
2. **性能开销**：保留更多步骤会增加推理时间

---

## 切换策略

如果发现当前策略不合适，可以随时切换：

```python
# 运行时切换（如果需要）
agent.memory_manager.aggressive_compression = False  # 切换到保守策略
```

---

## 历史版本兼容性

旧代码默认行为变化：

| 版本 | 默认策略 | 说明 |
|------|---------|------|
| v1.0 | 保守策略 | 使用 `get_compression_split_point_conservative` |
| v2.0 | 激进策略 | 使用 `get_compression_split_point`，添加历史代码追踪 |

如需恢复旧行为，设置 `aggressive_compression=False`。

---

## 最佳实践

1. **默认使用激进策略**：对大多数长任务来说更高效
2. **调试时使用保守策略**：保留更多细节便于问题定位
3. **根据任务调整**：
   - POC 验证、漏洞分析等长任务：激进策略
   - 快速查询、简单计算：保守策略
4. **监控 token 使用**：根据实际情况调整策略

