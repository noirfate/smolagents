import os
from typing import List, Optional

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
from smolagents.web_tools import WebTools

class CodeBrowserAgent:
    """代码浏览器Agent类，封装了Agent的创建和管理逻辑"""
    
    def __init__(
        self, 
        model_id: str = "gpt-5-chat",
        max_steps: int = 50,
        db_path: Optional[str] = None,
        code_dir: str = "code",
        work_dir: str = "workspace",
        enable_monitoring: bool = False,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_completion_tokens: int = 8192,
        verbosity_level: int = 2,
        planning_interval: int = 8
    ):
        """
        初始化代码浏览器Agent
        
        Args:
            model_id: 使用的LLM模型ID
            max_steps: Agent最大执行步数
            db_path: CodeQL数据库路径，如果为None则不启用CodeQL功能
            code_dir: 代码目录路径
            work_dir: CodeQL工作目录
            enable_monitoring: 是否启用Phoenix监控
            api_key: API密钥，如果为None则从环境变量获取
            base_url: API基础URL，如果为None则从环境变量获取
            max_completion_tokens: 最大完成token数
            verbosity_level: 详细程度级别
            planning_interval: 规划间隔
        """
        self.model_id = model_id
        self.max_steps = max_steps
        self.db_path = db_path
        self.code_dir = code_dir
        self.work_dir = work_dir
        self.enable_monitoring = enable_monitoring
        self.max_completion_tokens = max_completion_tokens
        self.verbosity_level = verbosity_level
        self.planning_interval = planning_interval
        
        # 设置API参数
        self.api_key = api_key or os.getenv("API_KEY")
        self.base_url = base_url or os.getenv("BASE_URL")
        
        # 初始化组件
        self._model = None
        self._agent = None
        self._tools = None
        
    @property
    def codeql_enabled(self) -> bool:
        """检查是否启用了CodeQL功能"""
        return self.db_path is not None
    
    @property
    def git_enabled(self) -> bool:
        """检查是否可以使用Git功能"""
        return self._check_git_availability()
    
    def _check_git_availability(self) -> bool:
        """检查Git是否可用"""
        try:
            import subprocess
            # 检查指定目录是否是Git仓库
            result = subprocess.run(
                ["git", "-C", self.code_dir, "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # 如果命令成功执行且返回包含.git的路径，则说明是Git仓库
            if result.returncode == 0:
                git_dir = result.stdout.strip()
                # 可能返回 ".git" 或者绝对路径如 "/path/to/repo/.git"
                return git_dir.endswith(".git") or git_dir == ".git"
            return False
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return False
        
    def _setup_monitoring(self) -> bool:
        """设置监控"""
        if self.enable_monitoring:
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
    
    def _validate_database(self) -> bool:
        """验证CodeQL数据库是否存在"""
        # 如果未启用CodeQL，跳过数据库验证
        if not self.codeql_enabled:
            return True
            
        if not os.path.exists(self.db_path):
            print(f"❌ 找不到CodeQL数据库: {self.db_path}")
            print("请确保已经创建了CodeQL数据库，例如:")
            print(f"codeql database create {self.db_path} --language=java --source-root=/path/to/source")
            return False
        return True
    
    def _create_model(self) -> LiteLLMModel:
        """创建LLM模型"""
        model_params = {
            "model_id": f"litellm_proxy/{self.model_id}",
            "max_completion_tokens": self.max_completion_tokens,
            "api_key": self.api_key,
            "base_url": self.base_url
        }
        return LiteLLMModel(**model_params)
    
    def _setup_tools(self) -> List:
        """设置代码分析所需的工具"""
        tools = []
        
        # Web工具 - 用于搜索CodeQL文档和示例
        web_tools = WebTools(self._model, text_limit=100000, search_engine="duckduckgo")
        tools.extend(web_tools.tools)

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
    
    def _create_tools(self) -> List:
        """创建工具列表"""
        if self._model is None:
            raise ValueError("模型尚未初始化，请先调用initialize()方法")
        return self._setup_tools()
    
    def _create_agent(self) -> MemoryCompressedCodeAgent:
        """创建Agent实例"""
        if self._model is None or self._tools is None:
            raise ValueError("模型和工具尚未初始化，请先调用initialize()方法")
            
        return MemoryCompressedCodeAgent(
            model=self._model,
            tools=self._tools,
            max_steps=self.max_steps,
            additional_authorized_imports=["*"],
            verbosity_level=self.verbosity_level,
            planning_interval=self.planning_interval,
            step_callbacks={
                PlanningStep: GoalDriftCallback()
            },
            name="code_browser_agent",
            description=self._get_agent_description(),
        )
    
    def _get_agent_description(self) -> str:
        """获取Agent描述"""
        base_description = """代码安全分析专家，具备强大的代码分析能力和丰富的漏洞知识，能够深入理解代码并发现其中的安全隐患，能够：

- **安全漏洞检测**：
   - 根据OWASP Top 10等标准进行分析
   - 检测注入攻击、访问控制、内存问题、条件竞争问题等
   - 识别业务逻辑漏洞和设计缺陷
   - 分析供应链和依赖安全问题

- **自适应分析**：
   - 根据项目特点调整分析策略
   - 结合上下文信息优化分析结果
   - 提供可操作的修复建议"""

        description_parts = []
        
        # 基础静态分析能力（始终包含）
        static_analysis = """

- **静态分析能力**：
   - 通过文件读取和模式匹配进行代码分析
   - 分析依赖关系和配置文件
   - 执行第三方分析工具

- **多语言支持**：
   - 支持Java、Python、JavaScript、Go、C/C++等主流语言
   - 理解各种语言的特性和常见漏洞模式
   - 能够分析框架特定的安全问题"""
        description_parts.append(static_analysis)
        
        # CodeQL 相关能力
        if self.codeql_enabled:
            codeql_description = """

- **动态CodeQL查询生成**：
   - 根据用户需求自动编写CodeQL查询语句
   - 理解不同编程语言的CodeQL语法和库
   - 生成针对特定漏洞类型或代码模式的查询
   - 优化查询性能和准确性

- **CodeQL语言精通**：
   - 熟练掌握CodeQL语法和查询逻辑
   - 了解各种编程语言的CodeQL库（Java、C/C++、Python、JavaScript、Go等）
   - 能够编写复杂的数据流分析查询
   - 理解CodeQL的类型系统和谓词逻辑"""
            description_parts.append(codeql_description)
        
        # Git 相关能力
        if self.git_enabled:
            git_description = """

- **Git历史分析**：
   - 分析提交历史和代码变更模式
   - 识别可疑的代码修改和回退
   - 追踪漏洞引入的时间点和作者
   - 分析分支合并和冲突解决情况
   - 检查敏感信息的历史泄露"""
            description_parts.append(git_description)
        
        # 组合所有能力描述
        return base_description + "".join(description_parts)
    
    def initialize(self) -> bool:
        """
        初始化Agent及其依赖组件
        
        Returns:
            bool: 初始化是否成功
        """
        # 设置监控
        if not self._setup_monitoring():
            return False
        
        # 验证数据库
        if not self._validate_database():
            return False
        
        # 创建模型
        self._model = self._create_model()
        
        # 创建工具
        self._tools = self._create_tools()
        
        # 创建Agent
        self._agent = self._create_agent()
        
        print(f"🎯 代码分析器启动")
        if self.codeql_enabled:
            print(f"📋 CodeQL数据库: {self.db_path}")
            print(f"📁 CodeQL工作目录: {self.work_dir}")
        else:
            print(f"📝 通用代码分析模式（未启用CodeQL）")
        print(f"📂 代码目录: {self.code_dir}")
        if self.git_enabled:
            print(f"🔧 Git仓库: 可用（支持历史分析）")
        else:
            print(f"🔧 Git仓库: 不可用")
        print(f"🤖 使用模型: {self.model_id}")
        print(f"📊 最大步数: {self.max_steps}")
        
        return True
    
    def build_analysis_task(self, user_input: str) -> str:
        """构建分析任务"""
        base_task = f"""
用户需求: {user_input}

---

## 工作环境
- 代码目录: {self.code_dir}
"""
        
        task_content = ""
        
        # CodeQL 相关内容
        if self.codeql_enabled:
            codeql_section = f"""
## CodeQL配置
### CodeQL环境
- CodeQL数据库路径: {self.db_path}
- CodeQL工作目录: {self.work_dir}

### CodeQL执行流程
1. 查询数据库语言: `codeql resolve database {self.db_path}`
2. 在{self.work_dir}目录下创建对应语言的`qlpack.yml`
3. 在{self.work_dir}目录下执行`codeql pack install`安装依赖
4. 在{self.work_dir}目录下创建ql查询文件
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

// 定义配置类或直接编写查询逻辑
from [变量声明]
where [查询条件]
select [结果选择], [消息]
```

**CodeQL查询示例（Go语言）:**
- 例1
```ql
/**
 * @id go/command-injection-taint
 * @name User-controlled data to command execution (Go)
 * @kind path-problem
 * @problem.severity error
 * @precision medium
 * @tags security; external/cwe/cwe-078
 */

import go
import semmle.go.dataflow.DataFlow
import codeql.dataflow.TaintTracking

/** 配置：定义源与汇 */
module CmdCfg implements DataFlow::ConfigSig {{
  /** 源：示例把 os.Getenv(...) 的结果当作“用户可控” */
  predicate isSource(DataFlow::Node src) {{
    exists(CallExpr c |
      c.getTarget().hasQualifiedName("os", "Getenv") and
      src.asExpr() = c
    )
  }}

  /** 汇：示例把 exec.Command* 的任一参数当作危险汇点 */
  predicate isSink(DataFlow::Node sink) {{
    exists(CallExpr c |
      (
        c.getTarget().hasQualifiedName("os/exec", "Command") or
        c.getTarget().hasQualifiedName("os/exec", "CommandContext")
      ) and
      sink.asExpr() = c.getAnArgument()
    )
  }}
}}

/** 实例化全局污点跟踪，并导入路径图 */
module CmdFlow = TaintTracking::Global<CmdCfg>;
import CmdFlow::PathGraph

from CmdFlow::PathNode source, CmdFlow::PathNode sink
where CmdFlow::flowPath(source, sink)
select sink.getNode(), source, sink,
  "User-controlled data reaches command execution."
```
- 例2
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

**执行CodeQL查询:**
- 保存查询: 使用write_file工具将查询保存到{self.work_dir}目录中
- 文件命名: 使用描述性名称，如 "find_sql_injection.ql" 或 "detect_hardcoded_secrets.ql"
- 执行查询: `codeql query run --database={self.db_path} {self.work_dir}/[查询文件.ql]`

### CodeQL注意事项
- 命令执行无需设置超时时间
- 执行遇到错误时请访问官方文档`https://codeql.github.com/codeql-standard-libraries/go`查找相关定义，根据官方最新定义进行相应修改
- 在生成 CodeQL 查询时，务必避免定义过宽的 source 或 sink。请限制在特定的函数、类型或包名范围内，而不是“所有函数调用”。
- 生成的查询必须包含【优化说明】注释，解释可能的性能风险点，以及如何进一步收缩范围。

#### CodeQL典型"旧知识误用 -> 新写法"对照
| 旧写法（错误）| 新写法（正确）|
| --- | --- |
| import semmle.code.go.dataflow.TaintTracking | import codeql.dataflow.TaintTracking |
| class Cfg extends TaintTracking::Configuration {{ … }} | module Cfg implements DataFlow::ConfigSig {{ … }} + module Flow = TaintTracking::Global<Cfg> |
| from DataFlow::PathNode s, DataFlow::PathNode t … | from Flow::PathNode source, Flow::PathNode sink …（Flow 为你实例化的模块）|
| c.getCalleeExpr().getReferent() | c.getTarget() |

"""
            task_content += codeql_section
        
        # 通用分析方法（始终包含）
        analysis_methods = """
## 代码分析方法
- **静态分析**: 通过读取和分析源代码文件
- **模式匹配**: 使用模式匹配工具查找特定代码片段
- **依赖分析**: 分析import/require语句和配置文件
- **配置审查**: 检查配置文件中的安全设置
"""
        
        # Git 相关内容
        if self.git_enabled:
            analysis_methods += """
- **Git历史分析**: 利用Git仓库信息进行深度分析

**Git分析命令:**
- `git log --oneline -n 20`: 查看最近的提交历史
- `git log --grep="security|fix|vuln|cve"`: 搜索安全相关提交
- `git log --author="用户名"`: 查看特定作者的提交
- `git show <commit-hash>`: 查看具体提交的变更内容
- `git blame <文件路径>`: 查看文件每行的最后修改信息
- `git log -p --follow <文件路径>`: 追踪文件的完整变更历史
- `git log --stat`: 查看提交的文件变更统计
- `git branch -a`: 查看所有分支
- `git diff <commit1>..<commit2>`: 比较两个提交之间的差异"""
        
        task_content += analysis_methods
        
        # 分析重点
        analysis_focus = """

### 分析重点
- 代码逻辑、功能、调用链
- 安全问题检查（SQL注入、XSS、命令注入、环境变量注入、竞争条件、UAF、逻辑漏洞、敏感信息泄露、缓冲区溢出等安全问题）
- 架构和设计问题"""
        
        if self.git_enabled:
            analysis_focus += """
- 历史漏洞模式（通过Git历史识别安全问题）
- 代码演进分析（识别可疑的快速修复或回退）
- 开发者行为分析（识别潜在的恶意或不当修改）"""
        
        task_content += analysis_focus
        
        # 工具使用
        tool_usage = """

### 工具使用
- 使用文件系统工具搜索、浏览和读取代码
- 使用系统命令执行必要的分析工具"""
        
        if self.git_enabled:
            tool_usage += """
- 使用Git命令分析代码历史和变更模式
- 结合Git信息和静态分析进行综合判断"""
        
        if self.codeql_enabled:
            tool_usage += """
- 使用CodeQL进行深度静态分析和数据流分析
- 结合CodeQL查询结果和其他分析方法"""
        
        task_content += tool_usage
        
        # 注意事项
        notes = """

## 注意事项
- 不用去互联网上搜索源码，源码在指定的代码目录下
- CodeQL遇到语法问题不要擅自修改，先去互联网上寻找解决方案，如访问CodeQL官方文档（https://codeql.github.com/codeql-standard-libraries/go/）
- 根据具体需求选择合适的分析方法和工具"""
        
        if self.codeql_enabled and self.git_enabled:
            notes += """
- 可以结合CodeQL查询和Git历史分析进行综合安全评估
- 优先使用CodeQL进行精确的静态分析，用Git历史补充上下文信息"""
        elif self.codeql_enabled:
            notes += """
- 优先使用CodeQL进行深度静态分析"""
        elif self.git_enabled:
            notes += """
- 充分利用Git历史信息辅助安全分析"""
        
        task_content += notes
        
        return base_task + task_content
        
    def run_interactive(self) -> None:
        """运行交互式对话模式"""
        if self._agent is None:
            raise ValueError("Agent尚未初始化，请先调用initialize()方法")
        
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
                self._agent.memory.reset()
                print("♻️ 已清空会话历史记忆。")
                continue

            if first:
                first = False
                user_input = self.build_analysis_task(user_input)

            # 继续在同一会话中运行，保留上下文
            follow_up_answer = self._agent.run(user_input, reset=False, max_steps=self.max_steps)
            print(f"Agent: {follow_up_answer}")
    
    def run_single_task(self, user_input: str, reset: bool = True) -> str:
        """
        运行单个任务
        
        Args:
            user_input: 用户输入
            reset: 是否重置Agent状态
            
        Returns:
            str: Agent的回复
        """
        if self._agent is None:
            raise ValueError("Agent尚未初始化，请先调用initialize()方法")
        
        task = self.build_analysis_task(user_input)
        return self._agent.run(task, reset=reset, max_steps=self.max_steps)
    
    @property
    def agent(self) -> Optional[MemoryCompressedCodeAgent]:
        """获取Agent实例"""
        return self._agent
    
    @property
    def model(self) -> Optional[LiteLLMModel]:
        """获取模型实例"""
        return self._model
    
    @property
    def tools(self) -> Optional[List]:
        """获取工具列表"""
        return self._tools
