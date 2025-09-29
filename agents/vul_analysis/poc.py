"""
POC验证器 - 基于大模型的自动化漏洞复现验证
负责读取漏洞分析报告并通过智能agent自动进行漏洞复现验证
"""

import argparse
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from smolagents import (
    LiteLLMModel,
    MemoryCompressedCodeAgent,
    GitHubTools,
    GoalDriftCallback,
    PlanningStep,
    ListDirectoryTool,
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    FileSearchTool,
    FileContentSearchTool,
    ShellTools,
)
from smolagents.web_tools import WebTools

load_dotenv(override=True)

class VulnerabilityReportReader:
    """漏洞分析报告读取器"""
    
    def __init__(self):
        pass
    
    def read_report(self, report_path: str) -> Dict[str, str]:
        """读取漏洞分析报告并提取关键信息"""
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取报告各个部分
            report_data = {
                'vulnerability_id': self._extract_vulnerability_id(content),
                'basic_info': self._extract_section(content, r'## 基础信息.*?(?=##|\Z)', '基础信息'),
                'analysis': self._extract_section(content, r'## 漏洞分析.*?(?=##|\Z)', '漏洞分析'),
                'reproduction': self._extract_section(content, r'## 漏洞复现.*?(?=##|\Z)', '漏洞复现'),
                'full_content': content
            }
            
            return report_data
            
        except Exception as e:
            print(f"❌ 读取报告失败: {e}")
            return {}
    
    def _extract_vulnerability_id(self, content: str) -> str:
        """提取漏洞ID"""
        match = re.search(r'# (CVE-\d{4}-\d+)', content)
        return match.group(1) if match else "Unknown"
    
    def _extract_section(self, content: str, pattern: str, section_name: str) -> str:
        """提取指定章节内容"""
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(0).strip()
        else:
            print(f"⚠️ 未找到 {section_name} 章节")
            return ""


class POCValidationAgent:
    """POC验证Agent - 基于大模型的智能漏洞复现验证器"""
    
    def __init__(self, model, max_steps=50):
        self.model = model
        self.max_steps = max_steps
        self.agent = self._create_agent()
    
    def _create_agent(self):
        """创建专门用于POC验证的智能agent"""
        
        # 基础工具
        web_tools = WebTools(model=self.model, text_limit=100000, search_engine="duckduckgo")
        
        # 尝试添加GitHub工具
        tools = web_tools.tools
        try:
            github_token = os.getenv("GITHUB_TOKEN")
            if github_token:
                github_tools = GitHubTools(github_token)
                tools.extend(github_tools.tools)
                print(f"✅ 已添加 {len(github_tools.tools)} 个GitHub工具")
        except Exception as e:
            print(f"⚠️ GitHub工具初始化失败: {e}")
        
        filesystem_tools = [
            ListDirectoryTool(),      # 列出目录内容
            ReadFileTool(),           # 读取文件
            WriteFileTool(),          # 写入文件
            EditFileTool(),           # 编辑文件
            FileSearchTool(),         # 搜索文件
            FileContentSearchTool(),  # 搜索文件内容
        ]
        tools.extend(filesystem_tools)

        # Shell工具 - 使用新的封装类
        shell_tools = ShellTools(
            default_page_size=20480,    # 20KB分页大小，超过此大小自动分页
            include_system_info=True    # 包含系统信息工具
        )
        tools.extend(shell_tools.tools)

        agent = MemoryCompressedCodeAgent(
            model=self.model,
            tools=tools,
            max_steps=self.max_steps,
            additional_authorized_imports=["*"],
            verbosity_level=2,
            planning_interval=8,
            step_callbacks={
                PlanningStep: GoalDriftCallback()
            },
            name="poc_validation_agent",
            description="""POC验证专家，具备强大的漏洞复现和验证能力。能够：

1. **环境搭建**：
   - 根据漏洞报告自动搭建复现环境
   - 配置Docker容器和依赖软件
   - 安装特定版本的受影响组件

2. **代码分析与调试**：
   - 理解和分析POC代码的工作原理
   - 识别和修复代码中的问题
   - 根据环境差异调整POC代码

3. **漏洞验证**：
   - 执行POC代码并观察结果
   - 分析执行日志和错误信息
   - 验证漏洞是否成功触发

4. **问题诊断**：
   - 当POC失败时，能够分析原因
   - 调整环境配置或代码实现
   - 多次迭代直到成功复现
            """,
        )
        
        return agent
    
    def validate_poc(self, report_data: Dict[str, str], output_path: Path) -> str:
        """执行POC验证任务"""
        print(f"🔬 开始POC验证: {report_data.get('vulnerability_id', 'Unknown')}")
        
        # 构建验证任务
        task = self._build_validation_task(report_data, output_path)
        
        # 执行验证
        result = self.agent.run(task)
        
        return result
    
    def _build_validation_task(self, report_data: Dict[str, str], output_path: Path) -> str:
        """构建POC验证任务"""
        
        full_content = report_data.get('full_content', '')
        
        task = f"""
# POC验证任务

你需要基于以下漏洞分析报告，进行完整的漏洞复现验证。

{full_content}

---

## 验证要求

### 1. 环境准备阶段
- 获取当前系统平台信息
- 仔细分析报告中的环境要求和依赖
- 镜像构建时，漏洞软件如果有现成的公开镜像则直接使用，尽量不要从基础镜像开始一步步构建
- 如果没有现成的Dockerfile或Dockerfile不完备，则根据需要自行创建或修改
- 确保所有依赖软件的版本正确（特别是受影响的版本）
- 根据dockerfile构建镜像，并启动容器

### 2. POC验证阶段
- 深入理解报告中提供的POC代码原理
- 分析POC的关键步骤和触发条件
- 如果POC不完整，根据技术分析补充完整的实现
- 在搭建的环境中执行POC代码，验证是否成功触发漏洞

### 3. 问题诊断阶段
- 如果执行失败，分析失败原因
- 可能的问题包括：
  * 环境配置不正确
  * 缺少必要的依赖库
  * POC代码有误或不完整  
  * 依赖版本不匹配
  * 系统差异导致的兼容性问题
- 根据分析结果调整环境或代码

### 4. 迭代优化阶段
- 基于诊断结果进行调整
- 重新执行验证
- 重复此过程直到成功复现或确认无法复现

## 重要注意事项

1. **镜像构建**: 使用dockerfile构建镜像时，不要设置超时时间，要等待其构建完成或异常退出
2. **验证执行**: 切实在当前系统中执行验证，调用shell工具执行docker命令、POC脚本或其他必要的命令
3. **持续调试**: 如果执行失败，要有耐心进行多轮改进调试
4. **完整验证**: 确保验证结果的可信度和完整性

现在开始执行POC验证任务。工作目录为: {output_path}
"""
        
        return task


class POCValidator:
    """POC验证器主类"""
    
    def __init__(self, model, max_steps=50):
        self.model = model
        self.max_steps = max_steps
        self.report_reader = VulnerabilityReportReader()
        self.poc_agent = POCValidationAgent(model, max_steps)
    
    def validate_vulnerability(self, report_path: str, output_dir: str) -> bool:
        """验证指定漏洞的POC"""
        
        # 读取分析报告
        print(f"📖 读取漏洞分析报告: {report_path}")
        report_data = self.report_reader.read_report(report_path)
        
        if not report_data:
            print("❌ 无法读取漏洞分析报告")
            return False
        
        vulnerability_id = report_data.get('vulnerability_id', 'Unknown')
        print(f"🎯 开始验证漏洞: {vulnerability_id}")
        
        # 创建输出目录
        output_path = Path(output_dir) / f"{vulnerability_id}_poc_validation"
        output_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # 执行POC验证
            result = self.poc_agent.validate_poc(report_data, output_path)
            
            # 保存验证结果
            result_file = output_path / f"poc_validation_result_{vulnerability_id}.md"
            with open(result_file, 'w', encoding='utf-8') as f:
                f.write(f"# POC验证结果 - {vulnerability_id}\n")
                f.write(f"> 验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(result)
            
            print(f"✅ POC验证完成，结果已保存到: {result_file}")
            return True
            
        except Exception as e:
            print(f"❌ POC验证过程中发生错误: {e}")
            return False


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="POC验证器 - 基于大模型的智能漏洞复现验证")
    parser.add_argument(
        "report_path",
        type=str,
        help="漏洞分析报告路径"
    )
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
        "--output-dir",
        type=str,
        default="output",
        help="输出目录，默认为output"
    )
    parser.add_argument(
        "--enable-monitoring",
        action="store_true",
        help="启用Phoenix监控"
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


def main():
    """主程序入口"""
    args = parse_args()
    
    # 设置监控
    if not setup_monitoring(args.enable_monitoring):
        return
    
    # 检查报告文件是否存在
    if not os.path.exists(args.report_path):
        print(f"❌ 找不到漏洞分析报告文件: {args.report_path}")
        return
    
    # 创建模型
    model_params = {
        "model_id": f"litellm_proxy/{args.model_id}",
        "max_completion_tokens": 8192,
        "api_key": os.getenv("API_KEY"),
        "base_url": os.getenv("BASE_URL")
    }
    model = LiteLLMModel(**model_params)
    
    print(f"🎯 POC验证器启动")
    print(f"📋 分析报告: {args.report_path}")
    print(f"🤖 使用模型: {args.model_id}")
    print(f"📊 最大步数: {args.max_steps}")
    print(f"📁 输出目录: {args.output_dir}")
    
    # 创建验证器并执行验证
    validator = POCValidator(model, args.max_steps)
    
    try:
        success = validator.validate_vulnerability(args.report_path, args.output_dir)
        
        if success:
            print("\n🎉 POC验证任务完成！")
        else:
            print("\n❌ POC验证任务失败！")
            
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断执行")
    except Exception as e:
        print(f"\n❌ 执行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
