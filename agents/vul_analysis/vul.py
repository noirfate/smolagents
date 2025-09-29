import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Callable

from vulnerability_info_collector import VulnerabilityInfoCollector
from vulnerability_analysis import VulnerabilityAnalyzer
from vulnerability_exploitation import VulnerabilityExploiter
from vulnerability_validator import VulnerabilityAnalysisValidator, QualityControlConfig

from smolagents import LiteLLMModel


class VulnerabilityAnalysisWorkflow:
    """
    漏洞分析工作流类
    
    封装了完整的三阶段漏洞分析过程：
    1. 信息收集
    2. 原因分析
    3. 利用分析
    """
    
    def __init__(self, model: LiteLLMModel, max_steps: int = 30, 
                 output_dir: str = "output", search_engine: str = "duckduckgo"):
        """
        初始化漏洞分析工作流
        
        Args:
            model: LLM模型实例
            max_steps: 每个阶段的最大执行步数
            output_dir: 输出目录
            search_engine: 搜索引擎选择
        """
        self.model = model
        self.max_steps = max_steps
        self.output_dir = output_dir
        self.search_engine = search_engine
        
        # 初始化各阶段分析器
        self.collector = VulnerabilityInfoCollector(model, max_steps, search_engine)
        self.analyzer = VulnerabilityAnalyzer(model, max_steps, search_engine, self.output_dir)
        self.exploiter = VulnerabilityExploiter(model, max_steps, search_engine)
        
        # 校验器（按需创建）
        self.validator = None
    
    def setup_validation(self, quality_config: QualityControlConfig):
        """设置质量校验"""
        if quality_config and quality_config.enable_validation:
            self.validator = VulnerabilityAnalysisValidator(self.model)
        self.quality_config = quality_config
    
    def get_or_create_output_directory(self, vulnerability_id: str) -> Path:
        """获取或创建输出目录"""
        output_path = Path(self.output_dir) / f"{vulnerability_id}"
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path
    
    def save_stage_result(self, result: str, stage_name: str, 
                         output_path: Path, vulnerability_id: str) -> Path:
        """保存阶段结果到文件"""
        filename = f"{stage_name}_{vulnerability_id}.md"
        filepath = output_path / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(result)
        
        print(f"✅ {stage_name}阶段结果已保存到: {filepath}")
        return filepath
    
    def load_existing_results(self, output_path: Path, vulnerability_id: str) -> Dict[Any, Any]:
        """加载已有的分析结果"""
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
    
    def enhance_task_with_guidance(self, base_task: str, guidance: str) -> str:
        """根据指导增强任务描述"""
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
    
    def execute_stage_with_validation(self, stage_name: str, executor_func: Callable[[str], str], 
                                    validator_func: Callable[[str], Tuple[bool, list, int, str]], 
                                    quality_config: Optional[QualityControlConfig]) -> str:
        """执行带质量校验的阶段任务"""
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
    
    def execute_stage1_info_collection(self, vulnerability_id: str, output_path: Path) -> Tuple[str, Path]:
        """第一阶段：漏洞基础信息收集"""
        print("\n" + "="*60)
        print("🔍 第一阶段：漏洞基础信息收集")
        print("="*60)
        
        base_task = f"""
        收集漏洞 {vulnerability_id} 的基础信息
        """
        
        def execute_with_guidance(guidance):
            enhanced_task = self.enhance_task_with_guidance(base_task, guidance)
            return self.collector.run(enhanced_task)
        
        # 执行带质量控制的任务
        result = self.execute_stage_with_validation(
            stage_name="信息收集",
            executor_func=execute_with_guidance,
            validator_func=lambda result: self.validator.validate_stage1_info_collection(result, vulnerability_id) if self.validator else (True, [], 100, ""),
            quality_config=self.quality_config
        )
        
        filepath = self.save_stage_result(result, "stage1_info", output_path, vulnerability_id)
        return result, filepath
    
    def execute_stage2_analysis(self, vulnerability_id: str, stage1_data: str, output_path: Path) -> Tuple[str, Path]:
        """第二阶段：漏洞原因分析"""
        print("\n" + "="*60)
        print("🔬 第二阶段：漏洞原因分析")
        print("="*60)
        
        base_task = f"""
        基于第一阶段收集的漏洞信息，请深入分析漏洞 {vulnerability_id} 的技术原理：
        
        第一阶段信息：
        {stage1_data}
        
        """
        
        def execute_with_guidance(guidance):
            enhanced_task = self.enhance_task_with_guidance(base_task, guidance)
            return self.analyzer.run(enhanced_task)
        
        # 执行带质量控制的任务
        result = self.execute_stage_with_validation(
            stage_name="技术分析",
            executor_func=execute_with_guidance,
            validator_func=lambda result: self.validator.validate_stage2_analysis(result, vulnerability_id) if self.validator else (True, [], 100, ""),
            quality_config=self.quality_config
        )
        
        filepath = self.save_stage_result(result, "stage2_analysis", output_path, vulnerability_id)
        return result, filepath
    
    def execute_stage3_exploitation(self, vulnerability_id: str, stage1_data: str, 
                                  stage2_data: str, output_path: Path) -> Tuple[str, Path]:
        """第三阶段：漏洞利用分析"""
        print("\n" + "="*60)
        print("⚔️ 第三阶段：漏洞利用分析")
        print("="*60)
        
        base_task = f"""
        基于前两个阶段的分析结果，请分析漏洞 {vulnerability_id} 的利用方法：
        
        第一阶段信息：
        {stage1_data}
        
        第二阶段分析：
        {stage2_data}
        
        """
        
        def execute_with_guidance(guidance):
            enhanced_task = self.enhance_task_with_guidance(base_task, guidance)
            return self.exploiter.run(enhanced_task)
        
        # 执行带质量控制的任务
        result = self.execute_stage_with_validation(
            stage_name="利用分析",
            executor_func=execute_with_guidance,
            validator_func=lambda result: self.validator.validate_stage3_exploitation(result, vulnerability_id) if self.validator else (True, [], 100, ""),
            quality_config=self.quality_config
        )
        
        filepath = self.save_stage_result(result, "stage3_exploitation", output_path, vulnerability_id)
        return result, filepath
    
    def generate_final_report(self, vulnerability_id: str, stage1_data: str, 
                            stage2_data: str, stage3_data: str, 
                            output_path: Path, model_id: str) -> Path:
        """生成最终报告"""
        final_report = f"""# {vulnerability_id}
> 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 使用模型: {model_id}

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
        
        final_report_path = self.save_stage_result(final_report, "final_report", output_path, vulnerability_id)
        return final_report_path
    
    def run_analysis(self, vulnerability_id: str, stage: str = "all", 
                    quality_config: Optional[QualityControlConfig] = None,
                    model_id: str = "unknown") -> Dict[str, Any]:
        """
        运行漏洞分析工作流
        
        Args:
            vulnerability_id: 漏洞ID
            stage: 执行阶段 ("all", "info", "analysis", "exploitation")
            quality_config: 质量控制配置
            model_id: 模型ID（用于报告）
        
        Returns:
            Dict: 包含各阶段结果的字典
        """
        # 设置质量校验
        if quality_config:
            self.setup_validation(quality_config)
        
        # 获取或创建输出目录
        output_path = self.get_or_create_output_directory(vulnerability_id)
        print(f"📁 输出目录: {output_path}")
        
        # 加载已有的分析结果
        results = self.load_existing_results(output_path, vulnerability_id)
        
        # 如果最终报告已存在且用户要求执行全部阶段，提示用户
        if results["final_exists"] and stage == "all":
            print("🎉 该漏洞的完整分析报告已存在！")
            print("如需重新分析，请删除输出目录或使用不同的输出目录。")
            return results
        
        print(f"🎯 开始分析漏洞: {vulnerability_id}")
        print(f"🤖 使用模型: {model_id}")
        print(f"📊 最大步数: {self.max_steps}")
        print(f"🔍 搜索引擎: {self.search_engine}")
        
        # 获取已有数据
        stage1_data = results[1]
        stage2_data = results[2]
        stage3_data = results[3]
        
        try:
            # 第一阶段：信息收集
            if stage in ["all", "info"] and not stage1_data:
                stage1_data, _ = self.execute_stage1_info_collection(vulnerability_id, output_path)
            
            # 第二阶段：原因分析  
            if stage in ["all", "analysis"] and not stage2_data:
                if stage1_data:
                    stage2_data, _ = self.execute_stage2_analysis(vulnerability_id, stage1_data, output_path)
                else:
                    print("❌ 第二阶段需要第一阶段的数据，请先运行信息收集阶段")
                    return results
            
            # 第三阶段：利用分析
            if stage in ["all", "exploitation"] and not stage3_data:
                if stage1_data and stage2_data:
                    stage3_data, _ = self.execute_stage3_exploitation(vulnerability_id, stage1_data, stage2_data, output_path)
                else:
                    print("❌ 第三阶段需要前两个阶段的数据")
                    return results
            
            # 生成最终报告
            if stage == "all" and stage1_data and stage2_data and stage3_data:
                final_report_path = self.generate_final_report(
                    vulnerability_id, stage1_data, stage2_data, stage3_data, 
                    output_path, model_id
                )
                print(f"\n🎉 漏洞分析完成！最终报告: {final_report_path}")
            
            # 更新结果
            results[1] = stage1_data
            results[2] = stage2_data  
            results[3] = stage3_data
            
        except KeyboardInterrupt:
            print("\n⚠️ 用户中断执行")
        except Exception as e:
            print(f"\n❌ 执行过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 显示已下载的仓库信息
            if hasattr(self, 'analyzer') and self.analyzer:
                repos = self.analyzer.list_repos()
                if repos:
                    print(f"📁 已缓存的代码仓库: {', '.join(repos)}")
                    print(f"📍 仓库目录: {self.analyzer.get_repo_dir()}")
        
        return results
    
    def list_cached_repos(self):
        """列出已缓存的代码仓库"""
        if hasattr(self, 'analyzer') and self.analyzer:
            repos = self.analyzer.list_repos()
            if repos:
                print(f"📁 已缓存的代码仓库: {', '.join(repos)}")
                print(f"📍 仓库目录: {self.analyzer.get_repo_dir()}")
                return repos
            else:
                print("📁 暂无缓存的代码仓库")
                return []
        return []
