import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from vulnerability_info_collector import VulnerabilityInfoCollector
from vulnerability_analysis import VulnerabilityAnalyzer
from vulnerability_exploitation import VulnerabilityExploiter

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

def stage_1_vulnerability_info_collection(vulnerability_id, model, max_steps, output_path):
    """第一阶段：漏洞基础信息收集"""
    print("\n" + "="*60)
    print("🔍 第一阶段：漏洞基础信息收集")
    print("="*60)
    
    collector = VulnerabilityInfoCollector(model, max_steps)
    
    task = f"""
    收集漏洞 {vulnerability_id} 的基础信息
    """
    result = collector.run(task)
    
    filepath = save_stage_result(result, "stage1_info", output_path, vulnerability_id)
    return result, filepath

def stage_2_vulnerability_analysis(vulnerability_id, stage1_data, model, max_steps, output_path):
    """第二阶段：漏洞原因分析"""
    print("\n" + "="*60)
    print("🔬 第二阶段：漏洞原因分析")
    print("="*60)
    
    analyzer = VulnerabilityAnalyzer(model, max_steps)
    
    task = f"""
    基于第一阶段收集的漏洞信息，请深入分析漏洞 {vulnerability_id} 的技术原理：
    
    第一阶段信息：
    {stage1_data}
    
    """
    
    result = analyzer.run(task)
    
    filepath = save_stage_result(result, "stage2_analysis", output_path, vulnerability_id)
    return result, filepath

def stage_3_vulnerability_exploitation(vulnerability_id, stage1_data, stage2_data, model, max_steps, output_path):
    """第三阶段：漏洞利用分析"""
    print("\n" + "="*60)
    print("⚔️ 第三阶段：漏洞利用分析")
    print("="*60)
    
    exploiter = VulnerabilityExploiter(model, max_steps)
    
    task = f"""
    基于前两个阶段的分析结果，请分析漏洞 {vulnerability_id} 的利用方法：
    
    第一阶段信息：
    {stage1_data}
    
    第二阶段分析：
    {stage2_data}
    
    """
    
    result = exploiter.run(task)
    
    filepath = save_stage_result(result, "stage3_exploitation", output_path, vulnerability_id)
    return result, filepath

def main():
    args = parse_args()
    
    # 设置监控
    if not setup_monitoring(args.enable_monitoring):
        return
    
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
                args.vulnerability_id, model, args.max_steps, output_path
            )
        
        # 第二阶段：原因分析  
        if args.stage in ["all", "analysis"] and not stage2_data:
            if stage1_data:
                stage2_data, _ = stage_2_vulnerability_analysis(
                    args.vulnerability_id, stage1_data, model, args.max_steps, output_path
                )
            else:
                print("❌ 第二阶段需要第一阶段的数据，请先运行信息收集阶段")
                return
        
        # 第三阶段：利用分析
        if args.stage in ["all", "exploitation"] and not stage3_data:
            if stage1_data and stage2_data:
                stage3_data, _ = stage_3_vulnerability_exploitation(
                    args.vulnerability_id, stage1_data, stage2_data, model, args.max_steps, output_path
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
