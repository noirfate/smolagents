import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from vulnerability_info_collector import VulnerabilityInfoCollector
from vulnerability_analysis import VulnerabilityAnalyzer
from vulnerability_exploitation import VulnerabilityExploiter
from vulnerability_validator import VulnerabilityAnalysisValidator, QualityControlConfig

from smolagents import (
    LiteLLMModel,
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

def get_or_create_output_directory(output_dir, vulnerability_id):
    """获取或创建输出目录"""
    output_path = Path(output_dir) / f"{vulnerability_id}"
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path

def save_stage_result(result, stage_name, output_path, vulnerability_id):
    """保存阶段结果到JSON文件"""
    filename = f"{stage_name}_{vulnerability_id}.md"
    filepath = output_path / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(result)

    print(f"✅ {stage_name}阶段结果已保存到: {filepath}")
    return filepath

def load_existing_results(output_path, vulnerability_id):
    """加载已有的分析结果，返回各阶段数据"""
    stage_files = {
        1: output_path / f"stage1_info_{vulnerability_id}.md",
        2: output_path / f"stage2_analysis_{vulnerability_id}.md", 
        3: output_path / f"stage3_exploitation_{vulnerability_id}.md",
        "final": output_path / f"final_report_{vulnerability_id}.md"
    }
    
    results = {}
    
    # 加载各阶段数据
    for stage_num in [1, 2, 3]:
        results[stage_num] = None
        if stage_files[stage_num].exists():
            try:
                with open(stage_files[stage_num], 'r', encoding='utf-8') as f:
                    data = f.read().strip()
                    if data:
                        results[stage_num] = data
                        print(f"✅ 加载阶段{stage_num}结果: {stage_files[stage_num]}")
            except Exception as e:
                print(f"⚠️ 加载阶段{stage_num}失败: {e}")
    
    # 检查最终报告
    results["final_exists"] = stage_files["final"].exists()
    if results["final_exists"]:
        print(f"✅ 发现最终报告: {stage_files['final']}")
    
    return results

def execute_stage_with_validation(stage_name, executor_func, validator_func, quality_config):
    """
    执行带质量校验的阶段任务
    
    Args:
        stage_name: 阶段名称
        executor_func: 执行函数，接受guidance参数
        validator_func: 校验函数
        quality_config: 质量控制配置
    
    Returns:
        str: 最终的分析结果
    """
    if not quality_config or not quality_config.enable_validation:
        # 不启用校验，直接执行
        return executor_func("")
    
    max_attempts = quality_config.max_retries + 1
    best_result = None
    best_score = 0
    current_guidance = ""
    
    for attempt in range(max_attempts):
        print(f"📝 执行{stage_name}阶段 - 第{attempt + 1}次尝试")
        if current_guidance and attempt > 0:
            print(f"🎯 基于上轮反馈进行改进...")
        
        try:
            # 执行任务（传入指导）
            result = executor_func(current_guidance)
            
            # 校验结果
            is_passed, problems, score, guidance = validator_func(result)
            
            print(f"📊 {stage_name}阶段质量评分: {score}/100")
            
            # 记录最好的结果
            if score > best_score:
                best_result = result
                best_score = score
            
            if is_passed and score >= quality_config.min_score_threshold:
                print(f"✅ {stage_name}阶段质量校验通过 (评分: {score}/100)")
                return result
            else:
                print(f"❌ {stage_name}阶段质量校验未通过 (评分: {score}/100)")
                if problems:
                    print("存在的问题:")
                    for i, problem in enumerate(problems[:3], 1):  # 最多显示3个问题
                        print(f"  {i}. {problem}")
                
                if attempt < max_attempts - 1:
                    print(f"🔄 准备基于反馈进行第{attempt + 2}次尝试...")
                    current_guidance = guidance  # 使用新的指导
                else:
                    print(f"⚠️ {stage_name}阶段已达到最大重试次数，使用最佳结果 (评分: {best_score}/100)")
        
        except Exception as e:
            print(f"❌ {stage_name}阶段执行出错: {e}")
            if attempt < max_attempts - 1:
                print(f"🔄 准备进行第{attempt + 2}次尝试...")
            else:
                if best_result:
                    print(f"⚠️ 使用之前的最佳结果 (评分: {best_score}/100)")
                else:
                    raise e
    
    return best_result if best_result else executor_func(current_guidance)

def enhance_task_with_guidance(base_task, guidance):
    """
    根据指导增强任务描述
    
    Args:
        base_task: 基础任务描述
        guidance: 行为指导
    
    Returns:
        str: 增强后的任务描述
    """
    if not guidance:
        return base_task
    
    enhanced_task = f"""
{base_task}

---

**重要：基于上一轮质量反馈的改进指导**

{guidance}

请特别关注上述指导，确保在本轮执行中重点改进这些方面。
"""
    return enhanced_task

def stage_1_vulnerability_info_collection(vulnerability_id, model, max_steps, output_path, quality_config=None):
    """第一阶段：漏洞基础信息收集"""
    print("\n" + "="*60)
    print("🔍 第一阶段：漏洞基础信息收集")
    print("="*60)
    
    collector = VulnerabilityInfoCollector(model, max_steps)
    validator = VulnerabilityAnalysisValidator(model) if quality_config and quality_config.enable_validation else None
    
    base_task = f"""
    收集漏洞 {vulnerability_id} 的基础信息
    """
    
    def execute_with_guidance(guidance):
        enhanced_task = enhance_task_with_guidance(base_task, guidance)
        return collector.run(enhanced_task)
    
    # 执行带质量控制的任务
    result = execute_stage_with_validation(
        stage_name="信息收集",
        executor_func=execute_with_guidance,
        validator_func=lambda result: validator.validate_stage1_info_collection(result, vulnerability_id) if validator else (True, [], 100, ""),
        quality_config=quality_config
    )
    
    filepath = save_stage_result(result, "stage1_info", output_path, vulnerability_id)
    return result, filepath

def stage_2_vulnerability_analysis(vulnerability_id, stage1_data, model, max_steps, output_path, quality_config=None):
    """第二阶段：漏洞原因分析"""
    print("\n" + "="*60)
    print("🔬 第二阶段：漏洞原因分析")
    print("="*60)
    
    analyzer = VulnerabilityAnalyzer(model, max_steps)
    validator = VulnerabilityAnalysisValidator(model) if quality_config and quality_config.enable_validation else None
    
    base_task = f"""
    基于第一阶段收集的漏洞信息，请深入分析漏洞 {vulnerability_id} 的技术原理：
    
    第一阶段信息：
    {stage1_data}
    
    """
    
    def execute_with_guidance(guidance):
        enhanced_task = enhance_task_with_guidance(base_task, guidance)
        return analyzer.run(enhanced_task)
    
    # 执行带质量控制的任务
    result = execute_stage_with_validation(
        stage_name="技术分析",
        executor_func=execute_with_guidance,
        validator_func=lambda result: validator.validate_stage2_analysis(result, vulnerability_id) if validator else (True, [], 100, ""),
        quality_config=quality_config
    )
    
    filepath = save_stage_result(result, "stage2_analysis", output_path, vulnerability_id)
    return result, filepath

def stage_3_vulnerability_exploitation(vulnerability_id, stage1_data, stage2_data, model, max_steps, output_path, quality_config=None):
    """第三阶段：漏洞利用分析"""
    print("\n" + "="*60)
    print("⚔️ 第三阶段：漏洞利用分析")
    print("="*60)
    
    exploiter = VulnerabilityExploiter(model, max_steps)
    validator = VulnerabilityAnalysisValidator(model) if quality_config and quality_config.enable_validation else None
    
    base_task = f"""
    基于前两个阶段的分析结果，请分析漏洞 {vulnerability_id} 的利用方法：
    
    第一阶段信息：
    {stage1_data}
    
    第二阶段分析：
    {stage2_data}
    
    """
    
    def execute_with_guidance(guidance):
        enhanced_task = enhance_task_with_guidance(base_task, guidance)
        return exploiter.run(enhanced_task)
    
    # 执行带质量控制的任务
    result = execute_stage_with_validation(
        stage_name="利用分析",
        executor_func=execute_with_guidance,
        validator_func=lambda result: validator.validate_stage3_exploitation(result, vulnerability_id) if validator else (True, [], 100, ""),
        quality_config=quality_config
    )
    
    filepath = save_stage_result(result, "stage3_exploitation", output_path, vulnerability_id)
    return result, filepath

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
    
    # 获取或创建输出目录
    output_path = get_or_create_output_directory(args.output_dir, args.vulnerability_id)
    print(f"📁 输出目录: {output_path}")
    
    # 加载已有的分析结果
    results = load_existing_results(output_path, args.vulnerability_id)
    
    # 如果最终报告已存在且用户要求执行全部阶段，提示用户
    if results["final_exists"] and args.stage == "all":
        print("🎉 该漏洞的完整分析报告已存在！")
        print("如需重新分析，请删除输出目录或使用不同的输出目录。")
        return
    
    # 创建模型
    model_params = {
        "model_id": f"litellm_proxy/{args.model_id}",
        "max_completion_tokens": 8192,
        "api_key": os.getenv("API_KEY"),
        "base_url": os.getenv("BASE_URL")
    }
    model = LiteLLMModel(**model_params)
    
    print(f"🎯 开始分析漏洞: {args.vulnerability_id}")
    print(f"🤖 使用模型: {args.model_id}")
    print(f"📊 最大步数: {args.max_steps}")
    
    # 获取已有数据
    stage1_data = results[1]
    stage2_data = results[2]
    stage3_data = results[3]
    
    # 执行阶段
    try:
        # 第一阶段：信息收集
        if args.stage in ["all", "info"] and not stage1_data:
            stage1_data, _ = stage_1_vulnerability_info_collection(
                args.vulnerability_id, model, args.max_steps, output_path, quality_config
            )
        
        # 第二阶段：原因分析  
        if args.stage in ["all", "analysis"] and not stage2_data:
            if stage1_data:
                stage2_data, _ = stage_2_vulnerability_analysis(
                    args.vulnerability_id, stage1_data, model, args.max_steps, output_path, quality_config
                )
            else:
                print("❌ 第二阶段需要第一阶段的数据，请先运行信息收集阶段")
                return
        
        # 第三阶段：利用分析
        if args.stage in ["all", "exploitation"] and not stage3_data:
            if stage1_data and stage2_data:
                stage3_data, _ = stage_3_vulnerability_exploitation(
                    args.vulnerability_id, stage1_data, stage2_data, model, args.max_steps, output_path, quality_config
                )
            else:
                print("❌ 第三阶段需要前两个阶段的数据")
                return
        
        # 生成最终报告
        if args.stage == "all" and stage1_data and stage2_data and stage3_data:
            final_report = f"""# {args.vulnerability_id}
> 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 使用模型: {args.model_id}

---

> 第一阶段：漏洞基础信息收集

{stage1_data}

---

> 第二阶段：漏洞原因分析

{stage2_data}

---

> 第三阶段：漏洞利用分析

{stage3_data}

---
"""
            
            final_report_path = save_stage_result(final_report, "final_report", output_path, args.vulnerability_id)
            print(f"\n🎉 漏洞分析完成！最终报告: {final_report_path}")
        
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断执行")
    except Exception as e:
        print(f"\n❌ 执行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
