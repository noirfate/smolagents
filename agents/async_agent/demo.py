"""
智能异步系统演示
展示CodeAgent如何动态进行任务拆解、分发和协调
"""

import os
import time
import random
from dotenv import load_dotenv
from smolagents import Tool, LiteLLMModel
from async_task_system import create_async_agent

# 加载环境变量
load_dotenv(override=True)

# 模拟一些需要异步处理的工具
class DataAnalysisTool(Tool):
    """数据分析工具 - 模拟耗时的数据分析"""
    
    name = "analyze_dataset"
    description = "Analyze a dataset and generate insights. This is a time-consuming operation."
    
    inputs = {
        "dataset_name": {
            "type": "string",
            "description": "Name of the dataset to analyze"
        },
        "analysis_type": {
            "type": "string",
            "description": "Type of analysis: trend, correlation, summary, prediction"
        },
        "parameters": {
            "type": "object",
            "description": "Additional analysis parameters",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, dataset_name: str, analysis_type: str, parameters: dict = None) -> str:
        """执行数据分析"""
        print(f"📊 Starting {analysis_type} analysis on {dataset_name}")
        
        # 模拟分析时间（2-6秒）
        analysis_time = random.uniform(2, 6)
        time.sleep(analysis_time)
        
        # 模拟分析结果
        results = {
            "trend": f"{dataset_name} shows upward trend with 15% growth rate",
            "correlation": f"Strong positive correlation (0.85) found in {dataset_name}",
            "summary": f"{dataset_name}: Mean=45.2, Std=12.8, Count=1000 records",
            "prediction": f"Forecast for {dataset_name}: 23% increase expected next quarter"
        }
        
        result = results.get(analysis_type, f"Analysis completed for {dataset_name}")
        print(f"✅ {analysis_type} analysis completed for {dataset_name}")
        
        return f"Analysis Result ({analysis_time:.1f}s): {result}"


class ReportGeneratorTool(Tool):
    """报告生成工具 - 模拟报告生成"""
    
    name = "generate_report"
    description = "Generate a comprehensive report based on analysis results."
    
    inputs = {
        "report_type": {
            "type": "string",
            "description": "Type of report: summary, detailed, executive"
        },
        "data_sources": {
            "type": "array",
            "description": "List of data sources or analysis results to include"
        },
        "title": {
            "type": "string",
            "description": "Report title",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, report_type: str, data_sources: list, title: str = None) -> str:
        """生成报告"""
        title = title or f"{report_type.title()} Report"
        print(f"📝 Generating {report_type} report: {title}")
        
        # 模拟报告生成时间
        generation_time = random.uniform(1, 3)
        time.sleep(generation_time)
        
        report = f"""
{title}
{'='*len(title)}

Report Type: {report_type.upper()}
Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
Data Sources: {len(data_sources)} sources

Key Findings:
{chr(10).join([f"• {source}" for source in data_sources[:5]])}
{'• ...' if len(data_sources) > 5 else ''}

Recommendations:
• Implement data-driven strategies based on findings
• Continue monitoring trends for future insights
• Consider expanding analysis to additional datasets

Report generated in {generation_time:.1f} seconds.
"""
        
        print(f"✅ Report generated: {title}")
        return report.strip()


class DatabaseQueryTool(Tool):
    """数据库查询工具 - 模拟数据库查询"""
    
    name = "query_database"
    description = "Execute a database query and return results."
    
    inputs = {
        "query": {
            "type": "string",
            "description": "SQL query to execute"
        },
        "database": {
            "type": "string",
            "description": "Database name"
        },
        "timeout": {
            "type": "number",
            "description": "Query timeout in seconds (default: 5)",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, query: str, database: str, timeout: float = 5) -> str:
        """执行数据库查询"""
        print(f"🗄️ Executing query on {database}: {query[:50]}...")
        
        # 模拟查询时间
        query_time = min(random.uniform(1, 4), timeout)
        time.sleep(query_time)
        
        # 模拟查询结果
        row_count = random.randint(10, 1000)
        result = f"Query executed successfully on {database}\nRows returned: {row_count}\nExecution time: {query_time:.1f}s\nSample data: [{{'id': 1, 'value': 42}}, {{'id': 2, 'value': 38}}, ...]"
        
        print(f"✅ Query completed on {database}")
        return result


# 创建数据科学家CodeAgent的函数
def create_data_scientist_agent(model):
    """创建专门的数据科学家CodeAgent"""
    from smolagents import CodeAgent
    
    data_scientist_prompt = """你是一位专业的数据科学家AI助手，专门处理复杂的数据科学和机器学习任务。

你的专长包括：
- 数据分析和统计建模
- 机器学习算法设计和优化  
- 预测模型构建
- 数据可视化
- 业务洞察提取

当收到任务时，你需要：
1. 分析任务要求和提供的数据
2. 选择合适的算法和方法
3. 进行模拟的数据处理和建模（使用sleep模拟计算时间）
4. 生成详细的分析报告，包括：
   - 使用的方法和算法
   - 关键发现和洞察
   - 模型性能指标
   - 业务建议

注意：
- 使用python_interpreter工具执行 `import time; time.sleep(随机3-8秒)` 来模拟复杂计算的耗时
- 在sleep期间可以输出"正在进行复杂的机器学习计算..."等状态信息
- 提供具体的技术细节和数值结果（可以模拟合理的数值）
- 保持专业的数据科学术语和分析思路
- 最后用final_answer输出完整的分析报告

工作流程示例：
1. 首先分析任务和数据
2. 使用python_interpreter执行: `import time, random; processing_time = random.uniform(3, 8); print(f"开始复杂的机器学习计算，预计需要{processing_time:.1f}秒..."); time.sleep(processing_time); print("计算完成！")`
3. 生成详细的分析报告
"""
    
    # 导入sleep工具用于模拟计算时间
    from smolagents.default_tools import PythonInterpreterTool
    
    # 创建数据科学家CodeAgent
    data_scientist = CodeAgent(
        tools=[PythonInterpreterTool()],  # 提供Python工具用于计算和sleep
        model=model,
        instructions=data_scientist_prompt,  # CodeAgent使用instructions而不是system_prompt
        max_steps=10,
        name="data_scientist",  # 直接在构造函数中设置name
        description="Expert data scientist for advanced analytics and machine learning tasks"  # 直接设置description
    )
    
    return data_scientist


def run_complex_scenario():
    """运行复杂的异步任务场景"""
    
    print("🚀 Starting Async Agent Demo")
    print("="*60)
    
    # 创建模型
    model = LiteLLMModel(
        model_id="litellm_proxy/deepseek-v3.1",
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
        max_completion_tokens=8192
    )
    
    # 创建工具和agents
    tools = [
        DataAnalysisTool(),
        ReportGeneratorTool(), 
        DatabaseQueryTool()
    ]
    
    # 创建真实的数据科学家CodeAgent
    data_scientist = create_data_scientist_agent(model)
    managed_agents = [data_scientist]
    
    async_agent = create_async_agent(
        tools=tools,
        managed_agents=managed_agents,
        model=model,
        max_workers=4,
        max_steps=25  # 增加步数限制，因为异步任务需要更多步骤
    )
    
    try:
        print("\n📋 Available Tools:", list(async_agent.tools.keys()))
        print("📋 Available Agents:", [agent.name for agent in managed_agents])
        
        # 场景1：复杂数据分析项目
        print("\n" + "="*60)
        print("🎯 Scenario 1: Complex Data Analysis Project")
        print("="*60)
        
        task = """
我需要完成一个综合的数据分析项目，包含以下任务：

1. 分析三个不同的数据集：
   - sales_2023_q1: 需要趋势分析
   - customer_behavior: 需要关联性分析  
   - market_data: 需要预测分析

2. 从数据库查询补充数据：
   - 查询产品表获取产品信息
   - 查询用户表获取用户统计

3. 让数据科学家进行深度机器学习分析

4. 最终生成一个执行摘要报告

请设计一个高效的并行处理方案来完成这个项目。你应该识别哪些任务可以并行执行，
合理安排任务顺序，并在适当的时候等待任务完成。
"""
        
        result = async_agent.run_with_async_guidance(task)
        print(f"\n✅ Result:\n{result}")
        
    except Exception as e:
        print(f"❌ Demo error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        async_agent.shutdown()
        print("\n🎉 Demo completed!")


def run_simple_scenario():
    """运行简单的演示场景"""
    
    print("🚀 Simple Async Agent Demo")
    print("="*40)
    
    tools = [DataAnalysisTool()]
    model = LiteLLMModel(
        model_id="litellm_proxy/deepseek-v3.1",
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
        max_completion_tokens=8192
    )
    
    async_agent = create_async_agent(
        tools=tools,
        model=model,
        max_workers=2,
        max_steps=15
    )
    
    try:
        simple_task = """
我需要分析两个数据集：sales_data 和 customer_data。
每个都需要趋势分析。请设计一个并行处理方案来提高效率。
"""
        
        result = async_agent.run_with_async_guidance(simple_task)
        print(f"\nResult: {result}")
        
    finally:
        async_agent.shutdown()


if __name__ == "__main__":
    # 可以选择运行复杂场景或简单场景
    run_simple_scenario()
    #run_complex_scenario()
