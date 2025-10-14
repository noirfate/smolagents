import argparse
import os

from dotenv import load_dotenv
from vul import VulnerabilityAnalysisWorkflow
from vulnerability_validator import QualityControlConfig
from poc import POCValidator

from smolagents import (
    LiteLLMModel,
    OpenAIServerModel
)

load_dotenv(override=True)

def parse_args():
    parser = argparse.ArgumentParser(description="漏洞分析工作流 - 三阶段分析")
    parser.add_argument(
        "vulnerability_id", 
        type=str, 
        help="漏洞标识符，如CVE编号: 'CVE-2024-1234' 或漏洞名称"
    )
    parser.add_argument("--model-id", type=str, default="gpt-5-chat")
    parser.add_argument(
        "--max-steps", 
        type=int, 
        default=30, 
        help="每个阶段Agent的最大执行步数，默认为30"
    )
    parser.add_argument(
        "--stage", 
        type=str, 
        choices=["all", "info", "analysis", "exploitation"], 
        default="all",
        help="选择执行的阶段: all(全部), info(信息收集), analysis(原因分析), exploitation(利用分析)"
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
    parser.add_argument(
        "--enable-validation",
        action="store_true",
        help="启用质量校验（默认禁用）"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="每个阶段最大重试次数，默认为2"
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=75,
        help="最低质量分数要求，默认为75"
    )
    parser.add_argument(
        "--search-engine",
        type=str,
        default="duckduckgo",
        choices=["duckduckgo", "google"],
        help="搜索引擎选择，默认为duckduckgo"
    )
    parser.add_argument(
        "--poc-validate",
        action="store_true",
        help="启用POC验证（默认禁用）"
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
        except ImportError as e:
            print(f"❌ 无法启用监控功能，缺少依赖包: {e}")
            return False
    return True


def main():
    args = parse_args()
    
    # 设置监控
    if not setup_monitoring(args.enable_monitoring):
        return
    
    # 设置质量控制配置
    quality_config = QualityControlConfig()
    quality_config.enable_validation = args.enable_validation
    quality_config.max_retries = args.max_retries
    quality_config.min_score_threshold = args.min_score
    
    print(f"🎯 质量控制配置:")
    print(f"   启用校验: {'是' if quality_config.enable_validation else '否'}")
    if quality_config.enable_validation:
        print(f"   最大重试: {quality_config.max_retries}次")
        print(f"   最低分数: {quality_config.min_score_threshold}分")
    print(f"   POC验证: {'是' if args.poc_validate else '否'}")
    
    # 创建模型
    model_params = {
        "model_id": f"{args.model_id}",
        #"max_completion_tokens": 8192,
        "api_key": os.getenv("API_KEY"),
        "api_base": os.getenv("BASE_URL")
    }
    #model = LiteLLMModel(**model_params)
    model = OpenAIServerModel(**model_params)
    
    # 创建漏洞分析工作流
    workflow = VulnerabilityAnalysisWorkflow(
        model=model,
        max_steps=args.max_steps,
        output_dir=args.output_dir,
        search_engine=args.search_engine
    )
    
    # 运行分析
    workflow.run_analysis(
        vulnerability_id=args.vulnerability_id,
        stage=args.stage,
        quality_config=quality_config,
        model_id=args.model_id
    )
    
    # POC验证（如果启用）
    if args.poc_validate:
        print("\n" + "="*60)
        print("🧪 开始POC验证")
        print("="*60)
        
        try:
            # 创建POC验证器
            poc_validator = POCValidator(model=model, max_steps=args.max_steps, search_engine=args.search_engine)
            
            # 查找最终报告文件
            from pathlib import Path
            output_path = Path(args.output_dir) / args.vulnerability_id
            final_report_path = output_path / f"final_report_{args.vulnerability_id}.md"
            
            if final_report_path.exists():
                print(f"📖 使用最终报告进行POC验证: {final_report_path}")
                success = poc_validator.validate_vulnerability(
                    report_path=str(final_report_path),
                    output_dir=str(output_path)
                )
                if success:
                    print("✅ POC验证完成")
                else:
                    print("❌ POC验证失败")
            else:
                print(f"⚠️ 未找到最终报告文件: {final_report_path}")
                print("请先完成完整的漏洞分析（--stage all）再进行POC验证")
                
        except Exception as e:
            print(f"❌ POC验证过程中发生错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
