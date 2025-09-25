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


# 模拟一个Managed Agent
class DataScientistAgent:
    """数据科学家Agent - 专门处理复杂的数据科学任务"""
    
    def __init__(self):
        self.name = "data_scientist"
        self.description = "Expert data scientist for advanced analytics and machine learning tasks"
    
    def __call__(self, task: str, additional_args: dict = None) -> str:
        """执行数据科学任务"""
        print(f"🔬 Data Scientist Agent: {task}")
        
        # 模拟复杂的数据科学工作
        processing_time = random.uniform(3, 8)
        time.sleep(processing_time)
        
        # 生成模拟结果
        result = f"""
Data Science Analysis Complete:

Task: {task}
Processing Time: {processing_time:.1f} seconds
Additional Context: {additional_args if additional_args else 'None'}

Findings:
• Applied advanced statistical methods
• Identified key patterns and anomalies  
• Generated predictive models with 87% accuracy
• Recommended optimization strategies

Technical Details:
- Algorithm: Random Forest with feature selection
- Cross-validation score: 0.89
- Feature importance: [price: 0.34, location: 0.28, time: 0.21, ...]
- Model confidence: High

Completed at: {time.strftime('%H:%M:%S')}
"""
        
        print(f"✅ Data Science task completed")
        return result.strip()


def run_complex_scenario():
    """运行复杂的异步任务场景"""
    
    print("🚀 Starting Async Agent Demo")
    print("="*60)
    
    # 创建工具和agents
    tools = [
        DataAnalysisTool(),
        ReportGeneratorTool(), 
        DatabaseQueryTool()
    ]
    
    managed_agents = [DataScientistAgent()]
    
    # 创建智能异步CodeAgent
    model = LiteLLMModel(
        model_id="litellm_proxy/deepseek-v3.1",
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
        max_completion_tokens=8192
    )
    
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
        
        scenario1_task = """
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
        
        result1 = async_agent.run_with_async_guidance(scenario1_task)
        print(f"\n✅ Scenario 1 Result:\n{result1}")
        
        # 场景2：实时监控和响应
        print("\n" + "="*60)
        print("🎯 Scenario 2: Real-time Monitoring and Response")
        print("="*60)
        
        scenario2_task = """
我需要建立一个实时监控系统，要求如下：

1. 同时监控5个不同的数据源：
   - website_traffic (需要摘要分析)
   - api_performance (需要趋势分析)
   - user_activity (需要关联分析)
   - system_metrics (需要异常检测)
   - business_kpi (需要预测分析)

2. 并行查询历史基线数据进行对比

3. 如果发现异常，立即生成告警报告

请实现这个监控系统，确保所有数据源都能并行处理，
并在检测到问题时快速响应。
"""
        
        result2 = async_agent.run_with_async_guidance(scenario2_task)
        print(f"\n✅ Scenario 2 Result:\n{result2}")
        
        # 场景3：批处理优化
        print("\n" + "="*60)
        print("🎯 Scenario 3: Batch Processing Optimization")
        print("="*60)
        
        scenario3_task = """
我有一个批处理任务需要优化，包括：

1. 处理10个数据集，每个都需要不同类型的分析
2. 为每个数据集生成单独的报告
3. 最后生成一个汇总报告

传统方法是串行处理，需要很长时间。请帮我设计一个并行处理方案，
最大化利用异步执行能力，减少总体处理时间。

数据集列表：dataset_1 到 dataset_10
分析类型：交替使用 trend, correlation, summary, prediction
"""
        
        result3 = async_agent.run_with_async_guidance(scenario3_task)
        print(f"\n✅ Scenario 3 Result:\n{result3}")
        
        # 显示最终统计
        print("\n" + "="*60)
        print("📊 Final Statistics")
        print("="*60)
        
        stats = async_agent.task_manager.get_statistics()
        print(f"Total tasks submitted: {stats['total_submitted']}")
        print(f"Total tasks completed: {stats['total_completed']}")
        print(f"Total tasks failed: {stats['total_failed']}")
        print(f"Tasks still pending: {stats['pending']}")
        print(f"Tasks still running: {stats['running']}")
        
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
