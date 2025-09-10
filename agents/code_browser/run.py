import argparse
import os

from dotenv import load_dotenv
from smolagents import (
    LiteLLMModel,
    MemoryCompressedCodeAgent,
    GoalDriftCallback,
    PlanningStep,
    ListDirectoryTool,
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    FileSearchTool,
    FileContentSearchTool,
    ExecuteCommandTool,
    GetSystemInfoTool,
)

load_dotenv(override=True)

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="代码浏览器 - 基于大模型的智能代码分析工具")
    parser.add_argument(
        "--model-id",
        type=str,
        default="gpt-5-chat",
        help="使用的LLM模型ID，默认为gpt-5-chat"
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=50,
        help="Agent最大执行步数，默认为50"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="codeql_db",
        help="codeql database路径"
    )
    parser.add_argument(
        "--enable-monitoring",
        action="store_true",
        help="启用Phoenix监控"
    )
    parser.add_argument(
        "--code",
        type=str,
        default="code",
        help="代码路径"
    )
    parser.add_argument(
        "--work",
        type=str,
        default="workspace",
        help="CodeQL工作目录"
    )
    
    return parser.parse_args()


def setup_monitoring(enable_monitoring):
    """设置监控"""
    if enable_monitoring:
        try:
            from phoenix.otel import register
            from openinference.instrumentation.smolagents import SmolagentsInstrumentor
            
            print("🔍 启用Phoenix监控，LLM输入输出将被记录...")
            register()
            SmolagentsInstrumentor().instrument()
            print("✅ 监控插桩已启用")
            return True
        except ImportError as e:
            print(f"❌ 无法启用监控功能，缺少依赖包: {e}")
            return False
    return True

def setup_tools(model):
    """设置代码分析所需的工具"""
    tools = []
    
    # Web工具 - 用于搜索CodeQL文档和示例
    #web_tools = WebTools(model, text_limit=100000, search_engine="duckduckgo")
    #tools.extend(web_tools.tools)

    # 文件系统工具 - 用于浏览和分析代码
    filesystem_tools = [
        ListDirectoryTool(),      # 列出目录内容
        ReadFileTool(),           # 读取文件
        WriteFileTool(),          # 写入文件
        EditFileTool(),           # 编辑文件
        FileSearchTool(),         # 搜索文件
        FileContentSearchTool(),  # 搜索文件内容
    ]
    tools.extend(filesystem_tools)

    # Shell工具 - 用于执行CodeQL命令
    shell_tools = [
        ExecuteCommandTool(),      # 执行系统命令
        GetSystemInfoTool(),       # 获取系统信息
    ]
    tools.extend(shell_tools)

    return tools


def build_analysis_task(user_input, db_path, code_dir, work_dir):
    """构建分析任务"""
    return f"""
用户需求: {user_input}

**工作环境:**
- CodeQL数据库路径: {db_path}
- CodeQL工作目录: {work_dir}
- 代码目录: {code_dir}

**CodeQL执行流程:**
1. 查询数据库语言: `codeql resolve database {db_path}`
2. 在{work_dir}目录下创建对应语言的`qlpack.yml`
3. 在{work_dir}目录下执行`codeql pack install`安装依赖
4. 在{work_dir}目录下创建ql查询文件
5. 执行查询

**CodeQL配置示例（qlpack.yml）:**
```yaml
name: my-go-queries           # 包名随意；只需全局唯一
version: 0.0.1
dependencies:                 # 告诉 CodeQL 需要哪些库
  codeql/go-all: "*"          # Go 标准库（必须）
```

**CodeQL查询结构:**

```ql
/**
 * @name [查询名称]
 * @description [详细描述]
 * @kind [path-problem/problem]
 * @problem.severity [error/warning/recommendation]
 * @id custom/[查询ID]
 */

import [相关库]
import DataFlow::PathGraph  // 如果需要路径分析

// 定义配置类或直接编写查询逻辑
from [变量声明]
where [查询条件]
select [结果选择], [消息]
```

**CodeQL查询示例（Go语言）:**
```ql
/**
 * @name Calls to NewImagePolicyWebhook (Go)
 * @kind problem
 * @description Lists every place where NewImagePolicyWebhook is invoked.
 */

import go

/** 认定一条调用是否针对 NewImagePolicyWebhook */
predicate isNewImagePolicyWebhookCall(CallExpr call) {{
  exists(Function f |
    call.getTarget() = f and
    f.getName() = "NewImagePolicyWebhook"
  )
  or
  call.getCalleeName() = "NewImagePolicyWebhook"
}}

from CallExpr call, Location loc
where
  isNewImagePolicyWebhookCall(call) and
  loc = call.getLocation()
select
  loc.getFile().getRelativePath(),   // 文件
  loc.getStartLine(),                // 行
  loc.getStartColumn(),              // 列
  "Call to NewImagePolicyWebhook"    // 说明
```

**常见CodeQL库:**
- Java: `import java`, `import semmle.code.java.dataflow.*`
- Python: `import python`, `import semmle.python.dataflow.*`
- JavaScript: `import javascript`, `import semmle.javascript.dataflow.*`
- C/C++: `import cpp`, `import semmle.code.cpp.dataflow.*`
- Go: `import go`, `import semmle.go.dataflow.*`, `import semmle.go.security.*`

**执行CodeQL查询:**
- 保存查询: 使用write_file工具将查询保存到{work_dir}目录中
- 文件命名: 使用描述性名称，如 "find_sql_injection.ql" 或 "detect_hardcoded_secrets.ql"
- 执行查询: `codeql query run --database={db_path} {work_dir}/[查询文件.ql]`

**注意事项:**
- 不用去互联网上搜索源码，源码在{code_dir}目录下
- 命令执行无需设置超时时间
"""


def main():
    """主程序入口"""
    args = parse_args()
    
    # 设置监控
    if not setup_monitoring(args.enable_monitoring):
        return
    
    # 检查CodeQL数据库是否存在
    if not os.path.exists(args.db):
        print(f"❌ 找不到CodeQL数据库: {args.db}")
        print("请确保已经创建了CodeQL数据库，例如:")
        print(f"codeql database create {args.db} --language=java --source-root=/path/to/source")
        return
    
    # 创建模型
    model_params = {
        "model_id": f"litellm_proxy/{args.model_id}",
        "max_completion_tokens": 8192,
        "api_key": os.getenv("API_KEY"),
        "base_url": os.getenv("BASE_URL")
    }
    model = LiteLLMModel(**model_params)
    tools = setup_tools(model)

    agent = MemoryCompressedCodeAgent(
        model=model,
        tools=tools,
        max_steps=args.max_steps,
        additional_authorized_imports=["*"],
        verbosity_level=2,
        planning_interval=8,
        step_callbacks={
            PlanningStep: GoalDriftCallback()
        },
        name="code_browser_agent",
        description="""代码分析专家，具备强大的代码分析能力和CodeQL查询编写能力。能够：

1. **动态CodeQL查询生成**：
   - 根据用户需求自动编写CodeQL查询语句
   - 理解不同编程语言的CodeQL语法和库
   - 生成针对特定漏洞类型或代码模式的查询
   - 优化查询性能和准确性

2. **CodeQL语言精通**：
   - 熟练掌握CodeQL语法和查询逻辑
   - 了解各种编程语言的CodeQL库（Java、C/C++、Python、JavaScript、Go等）
   - 能够编写复杂的数据流分析查询
   - 理解CodeQL的类型系统和谓词逻辑

3. **安全漏洞检测**：
   - 根据OWASP Top 10等标准生成相应查询
   - 检测注入攻击、访问控制、加密问题等
   - 识别业务逻辑漏洞和设计缺陷
   - 分析供应链和依赖安全问题

4. **代码质量分析**：
   - 生成检测代码异味的查询
   - 分析性能问题和资源泄露
   - 检测反模式和设计问题
   - 评估代码复杂度和可维护性

5. **自适应分析**：
   - 根据项目特点调整分析策略
   - 结合上下文信息优化查询结果
   - 提供可操作的修复建议
            """,
        )
    
    print(f"🎯 代码分析器启动")
    print(f"📋 CodeQL数据库: {args.db}")
    print(f"🤖 使用模型: {args.model_id}")
    print(f"📊 最大步数: {args.max_steps}")
    
    first = True
    print("\n🗣 进入对话模式。提示：输入 'exit' 或 'quit' 退出，会话内输入 '/reset' 可清空历史记忆。\n")

    while True:
        try:
            user_input = input("user>: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 退出对话模式。")
            break

        if not user_input:
            continue

        lower_input = user_input.lower()
        if lower_input in ("exit", "quit", "q"):
            print("👋 退出对话模式。")
            break

        if lower_input.startswith("/reset"):
            # 清空记忆但保留系统提示
            agent.memory.reset()
            print("♻️ 已清空会话历史记忆。")
            continue

        if first:
            first = False
            user_input = build_analysis_task(user_input, args.db, args.code, args.work)

        # 继续在同一会话中运行，保留上下文
        follow_up_answer = agent.run(user_input, reset=False, max_steps=args.max_steps)
        print(f"Agent: {follow_up_answer}")


if __name__ == "__main__":
    main()