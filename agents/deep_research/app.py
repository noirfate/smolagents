import os
import sys
import io
import threading
import time
import re
from contextlib import redirect_stdout, redirect_stderr
import gradio as gr
from run import create_agent
from dotenv import load_dotenv

load_dotenv(override=True)

# 支持的模型列表
SUPPORTED_MODELS = [
    "o1",
    "gpt-4o", 
    "o3",
    "gpt-4.5-preview",
    "claude-sonnet-4-20250514",
    "ark-deepseek-r1-250528",
    "gemini-2.5-pro"
]

class StreamCapture:
    """捕获输出流用于实时显示"""
    def __init__(self):
        self.output = []
        self.lock = threading.Lock()
    
    def write(self, text):
        with self.lock:
            # 保留原始文本，稍后转换为HTML
            self.output.append(text)
        return len(text)
    
    def flush(self):
        pass
    
    def get_output(self):
        with self.lock:
            return ''.join(self.output)
    
    def get_html_output(self):
        """获取HTML格式的输出"""
        with self.lock:
            raw_text = ''.join(self.output)
            try:
                return ansi_to_html(raw_text)
            except Exception:
                # 如果转换失败，回退到简单清理并应用默认颜色
                cleaned_text = clean_ansi_codes(raw_text)
                return f'<span style="color: #e5e7eb;">{cleaned_text}</span>'
    
    def clear(self):
        with self.lock:
            self.output.clear()

def ansi_to_html(text):
    """将ANSI转义序列转换为HTML"""
    # ANSI颜色映射（适配深色背景）
    ansi_colors = {
        '30': '#6b7280',  # 黑色（改为灰色，在深色背景上可见）
        '31': '#f87171',  # 红色
        '32': '#4ade80',  # 绿色
        '33': '#fbbf24',  # 黄色
        '34': '#60a5fa',  # 蓝色
        '35': '#c084fc',  # 洋红
        '36': '#22d3ee',  # 青色
        '37': '#e5e7eb',  # 白色
        '90': '#9ca3af',  # 亮黑色（灰色）
        '91': '#ff6b6b',  # 亮红色
        '92': '#51cf66',  # 亮绿色
        '93': '#ffd43b',  # 亮黄色
        '94': '#74c0fc',  # 亮蓝色
        '95': '#f06292',  # 亮洋红
        '96': '#22d3ee',  # 亮青色
        '97': '#f8f9fa',  # 亮白色
    }
    
    # 当前样式状态
    current_style = {
        'color': '#e5e7eb',  # 默认终端文字颜色（确保在深色背景上可见）
        'background': 'transparent',
        'bold': False,
        'italic': False,
        'underline': False
    }
    
    result = []
    i = 0
    
    while i < len(text):
        # 查找ANSI转义序列
        if text[i:i+1] == '\x1b' or text[i:i+1] == '[':
            # 找到转义序列的结束位置
            j = i + 1
            if text[i:i+1] == '\x1b' and i + 1 < len(text) and text[i+1] == '[':
                j = i + 2
            elif text[i:i+1] == '[':
                j = i + 1
            
            # 查找序列结束
            while j < len(text) and text[j] not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz':
                j += 1
            
            if j < len(text):
                j += 1  # 包含结束字符
                ansi_seq = text[i:j]
                
                # 解析ANSI序列
                if 'm' in ansi_seq:  # 颜色/样式序列
                    # 提取数字部分
                    numbers = re.findall(r'\d+', ansi_seq)
                    i_num = 0
                    while i_num < len(numbers):
                        num = numbers[i_num]
                        if num == '0':  # 重置
                            current_style = {
                                'color': '#e5e7eb',  # 确保重置后文字可见
                                'background': 'transparent',
                                'bold': False,
                                'italic': False,
                                'underline': False
                            }
                        elif num == '1':  # 粗体
                            current_style['bold'] = True
                        elif num == '3':  # 斜体
                            current_style['italic'] = True
                        elif num == '4':  # 下划线
                            current_style['underline'] = True
                        elif num in ansi_colors:  # 前景色
                            current_style['color'] = ansi_colors[num]
                        elif num == '38':  # 扩展前景色
                            if i_num + 1 < len(numbers):
                                if numbers[i_num + 1] == '2':  # RGB
                                    if i_num + 4 < len(numbers):
                                        r = numbers[i_num + 2]
                                        g = numbers[i_num + 3] 
                                        b = numbers[i_num + 4]
                                        current_style['color'] = f'rgb({r},{g},{b})'
                                        i_num += 4  # 跳过已处理的数字
                                    else:
                                        i_num += 1
                                elif numbers[i_num + 1] == '5':  # 256色
                                    if i_num + 2 < len(numbers):
                                        color_index = int(numbers[i_num + 2])
                                        # 简化的256色到RGB映射
                                        if color_index < 16:
                                            current_style['color'] = list(ansi_colors.values())[color_index % 8]
                                        else:
                                            # 简单的灰度或颜色映射
                                            current_style['color'] = f'rgb({color_index},{color_index},{color_index})'
                                        i_num += 2
                                    else:
                                        i_num += 1
                                else:
                                    i_num += 1
                            else:
                                i_num += 1
                        else:
                            pass
                        
                        i_num += 1
                
                i = j
            else:
                i += 1
        else:
            # 普通字符
            char = text[i]
            
            # HTML实体转义
            if char == '<':
                char = '&lt;'
            elif char == '>':
                char = '&gt;'
            elif char == '&':
                char = '&amp;'
            elif char == '"':
                char = '&quot;'
            
            # 处理特殊Unicode字符（框线）
            box_chars = {
                '╭': '┌', '╮': '┐', '╯': '┘', '╰': '└',
                '─': '─', '│': '│', '┬': '┬', '┴': '┴',
                '├': '├', '┤': '┤', '┼': '┼'
            }
            
            if char in box_chars:
                char = box_chars[char]
            
            # 应用当前样式
            style_parts = []
            # 总是应用颜色样式，确保文字可见
            style_parts.append(f"color: {current_style['color']}")
            if current_style['background'] != 'transparent':
                style_parts.append(f"background-color: {current_style['background']}")
            if current_style['bold']:
                style_parts.append("font-weight: bold")
            if current_style['italic']:
                style_parts.append("font-style: italic")
            if current_style['underline']:
                style_parts.append("text-decoration: underline")
            
            style_str = '; '.join(style_parts)
            result.append(f'<span style="{style_str}">{char}</span>')
            
            i += 1
    
    return ''.join(result)

def clean_ansi_codes(text):
    """备用函数：简单清理ANSI字符（如果HTML转换失败）"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def enable_monitoring():
    """启用Phoenix监控"""
    try:
        from phoenix.otel import register
        from openinference.instrumentation.smolagents import SmolagentsInstrumentor
        
        register()
        SmolagentsInstrumentor().instrument()
        return "✅ Phoenix监控已启用"
    except ImportError as e:
        return f"❌ 无法启用监控: {e}"

def create_research_interface():
    """创建研究界面"""
    
    # 只记录模型选择，不预先创建agent
    current_model = "gemini-2.5-pro"
    monitoring_enabled = False
    
    def update_model_selection(model_id):
        """更新模型选择（不创建agent）"""
        nonlocal current_model
        current_model = model_id
        return f"✅ 已选择模型: {model_id}"
    
    def toggle_monitoring(enable):
        """切换监控状态"""
        nonlocal monitoring_enabled
        if enable and not monitoring_enabled:
            result = enable_monitoring()
            monitoring_enabled = True
            return result
        elif enable:
            return "✅ 监控已经启用"
        else:
            monitoring_enabled = False
            return "📝 监控已禁用"
    
    def run_research_stream(question, model_id, max_steps, enable_monitoring_flag):
        """流式执行研究任务"""
        if not question.strip():
            yield ('<div class="terminal-output"><pre><span style="color: #e5e7eb;">请输入研究问题</span></pre></div>', 
                   '<div class="result-display">请输入研究问题开始</div>')
            return
        
        # 确保max_steps是有效的正整数
        try:
            max_steps = int(max_steps) if max_steps else 20
            if max_steps <= 0:
                max_steps = 20
        except (ValueError, TypeError):
            max_steps = 20
        
        # 处理监控状态
        monitoring_status = toggle_monitoring(enable_monitoring_flag)
        status_html = f'<div class="terminal-output"><pre>🔧 系统状态: {monitoring_status}\n\n'
        
        # 更新当前选择的模型（如果不同）
        if model_id != current_model:
            update_model_selection(model_id)
            status_html += f'🔄 使用模型: {model_id}\n\n'
        
        # 现在创建agent（只在真正需要时创建）
        status_html += f'🤖 正在创建Agent ({model_id}, max_steps={max_steps})...\n'
        try:
            current_agent = create_agent(model_id, max_steps, use_browser=True)  # 默认启用浏览器功能
            status_html += f'✅ Agent创建成功\n\n'
        except Exception as e:
            status_html += f'❌ Agent创建失败: {str(e)}</pre></div>'
            yield (status_html, f'<div class="result-display error">❌ Agent创建失败: {str(e)}</div>')
            return
        
        # 创建输出捕获器
        capture = StreamCapture()
        
        try:
            status_html += f'🚀 开始研究: {question}\n\n{"="*60}\n\n'
            yield (status_html + '</pre></div>', '<div class="result-display">🔄 研究进行中...</div>')
            
            # 在单独的线程中运行agent，同时捕获输出
            result_container = {'result': None, 'error': None}
            
            def run_agent():
                try:
                    with redirect_stdout(capture), redirect_stderr(capture):
                        result = current_agent.run(question)
                        result_container['result'] = result
                except Exception as e:
                    result_container['error'] = str(e)
            
            # 启动agent执行线程
            agent_thread = threading.Thread(target=run_agent)
            agent_thread.start()
            
            # 实时显示执行过程
            last_html_output = ""
            step_count = 0
            
            while agent_thread.is_alive():
                current_html_output = capture.get_html_output()
                if current_html_output != last_html_output:
                    step_count += 1
                    terminal_html = f'''
                    <div class="terminal-output">
                        <pre>🔧 系统状态: {monitoring_status}

🚀 开始研究: {question}

{"="*60}

{current_html_output}

🔄 执行中... (步骤 {step_count})</pre>
                    </div>
                    '''
                    yield (terminal_html, '<div class="result-display">🔄 研究进行中... 正在执行步骤...</div>')
                    last_html_output = current_html_output
                time.sleep(0.5)  # 每0.5秒更新一次
            
            # 等待线程完成
            agent_thread.join()
            
            # 显示最终结果
            final_html_output = capture.get_html_output()
            
            if result_container['error']:
                final_process_html = f'''
                <div class="terminal-output">
                    <pre>🔧 系统状态: {monitoring_status}

🚀 开始研究: {question}

{"="*60}

{final_html_output}

❌ 研究失败: {result_container['error']}</pre>
                </div>
                '''
                final_result_html = f'''
                <div class="result-display error">
                    <h3>❌ 研究失败</h3>
                    <p><strong>错误信息:</strong> {result_container['error']}</p>
                    <p><strong>研究问题:</strong> {question}</p>
                </div>
                '''
            else:
                monitoring_info = f'\n\n监控状态: {monitoring_status}' if enable_monitoring_flag else ''
                final_process_html = f'''
                <div class="terminal-output">
                    <pre>🔧 系统状态: {monitoring_status}

🚀 开始研究: {question}

{"="*60}

{final_html_output}

✅ 研究完成

{"="*60}

📋 最终结果:

{result_container['result']}{monitoring_info}</pre>
                </div>
                '''
                # 处理换行符
                formatted_result = result_container['result'].replace('\n', '<br/>') if result_container['result'] else '无结果'
                monitoring_info_html = f'<p class="monitoring-info"><strong>监控状态:</strong> {monitoring_status}</p>' if enable_monitoring_flag else ''
                
                final_result_html = f'''
                <div class="result-display success">
                    <h3>✅ 研究完成</h3>
                    <div class="final-answer">
                        {formatted_result}
                    </div>
                    {monitoring_info_html}
                </div>
                '''
            
            yield (final_process_html, final_result_html)
                
        except Exception as e:
            error_process_html = f'''
            <div class="terminal-output">
                <pre>❌ 研究过程中出现错误: {str(e)}</pre>
            </div>
            '''
            error_result_html = f'''
            <div class="result-display error">
                <h3>❌ 系统错误</h3>
                <p><strong>错误信息:</strong> {str(e)}</p>
                <p><strong>研究问题:</strong> {question}</p>
            </div>
            '''
            yield (error_process_html, error_result_html)
    

    
    # 创建Gradio界面
    with gr.Blocks(
        title="🔬 Open Deep Research - AI研究助手",
        theme=gr.themes.Soft(),
        css="""
        .gradio-container {
            max-width: 100% !important;
            width: 100% !important;
            padding: 0 20px !important;
        }
        .research-header {
            text-align: center;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .main {
            width: 100% !important;
            max-width: 100% !important;
        }
        .terminal-output {
            background-color: #1a1a1a !important;
            color: #e2e8f0 !important;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
            font-size: 14px !important;
            line-height: 1.4 !important;
            padding: 15px !important;
            border-radius: 8px !important;
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            overflow-x: auto !important;
            border: 1px solid #374151 !important;
        }
        .terminal-output pre {
            margin: 0 !important;
            padding: 0 !important;
            background: transparent !important;
            border: none !important;
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            color: inherit !important;
        }
        .result-display {
            background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #cbd5e1;
            margin: 10px 0;
        }
        .result-display.success {
            background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
            border-color: #86efac;
        }
        .result-display.error {
            background: linear-gradient(135deg, #fef2f2 0%, #fecaca 100%);
            border-color: #fca5a5;
        }
        .result-display h3 {
            margin: 0 0 15px 0;
            color: #1e293b;
            font-size: 18px;
        }
        .result-display.success h3 {
            color: #166534;
        }
        .result-display.error h3 {
            color: #dc2626;
        }
        .final-answer {
            background: white;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #10b981;
            line-height: 1.6;
            color: #374151;
            font-size: 15px;
        }
        .monitoring-info {
            margin-top: 12px;
            font-size: 14px;
            color: #6b7280;
            font-style: italic;
        }
        """
    ) as demo:
        
        # 标题和说明
        gr.HTML("""
        <div class="research-header">
            <h1>🔬 Open Deep Research</h1>
            <p>AI驱动的深度研究助手 - 支持网络搜索、数据分析和可视化</p>
        </div>
        """)
        
        with gr.Row():
            with gr.Column(scale=2):
                # 研究问题输入
                question_input = gr.Textbox(
                    label="🎯 研究问题",
                    placeholder="例如: How many studio albums did Mercedes Sosa release before 2007?",
                    lines=3,
                    max_lines=5
                )
                
                # 模型选择
                model_selector = gr.Dropdown(
                    choices=SUPPORTED_MODELS,
                    value=f"{current_model}",
                    label="🤖 选择AI模型",
                    info="不同模型有不同的特点和能力"
                )
                
                # 最大步数设置
                max_steps_input = gr.Number(
                    value=20,
                    label="⚙️ 最大执行步数",
                    info="Agent执行的最大步数，数值越大能处理更复杂任务但耗时更长"
                )
                
                # 监控开关
                monitoring_checkbox = gr.Checkbox(
                    label="🔍 启用Phoenix监控",
                    value=False,
                    info="监控LLM输入输出，需要安装相关依赖包"
                )
                
                with gr.Row():
                    research_btn = gr.Button("🔍 开始研究", variant="primary", size="lg")
                    clear_btn = gr.Button("🗑️ 清空", variant="secondary")
            
            with gr.Column(scale=1):
                # 系统状态
                gr.Markdown("### 📊 系统状态")
                status_display = gr.Textbox(
                    label="当前状态",
                    value=f"✅ 已准备就绪 | 当前模型: {current_model}",
                    interactive=False,
                    lines=2
                )
                
                # 功能说明
                gr.Markdown("""
                ### 🚀 功能特点
                - 🌐 **智能搜索**: 自动搜索和分析网络信息
                - 🔥 **真实浏览器**: 使用Chrome浏览器执行JS，获取纯文本内容
                - 📊 **GitHub集成**: 查询代码仓库和技术信息  
                - 💻 **代码执行**: 专门的Python代码编写和执行agent
                - 🤖 **多模型**: 支持多种AI模型
                - ⚙️ **可调步数**: 灵活设置Agent执行步数
                - 🧠 **记忆压缩**: 基于Planning周期的智能记忆管理
                """)
        
        # 最终结果显示区域
        final_result_output = gr.HTML(
            label="📋 研究结果",
            value='<div class="result-display">准备就绪，等待开始研究...</div>'
        )
        
        # 运行过程显示区域（可折叠）
        with gr.Accordion("🔍 查看详细执行过程", open=False):
            process_output = gr.HTML(
                value="""
                <div class="terminal-output">
                    <pre>等待开始研究...

💡 提示: 开始研究后，您将看到Agent执行的详细步骤</pre>
                </div>
                """,
                elem_classes=["terminal-output"]
            )
        
        # 事件绑定
        research_btn.click(
            fn=run_research_stream,
            inputs=[question_input, model_selector, max_steps_input, monitoring_checkbox],
            outputs=[process_output, final_result_output],
            show_progress=True
        )
        
        model_selector.change(
            fn=lambda model_id: update_model_selection(model_id),
            inputs=[model_selector],
            outputs=[status_display],
            show_progress=True
        )
        
        clear_btn.click(
            fn=lambda: ("", 
                       """<div class="terminal-output"><pre><span style="color: #e5e7eb;">等待开始研究...

💡 提示: 开始研究后，您将看到Agent执行的详细步骤</span></pre></div>""",
                       '<div class="result-display">准备就绪，等待开始研究...</div>'),
            outputs=[question_input, process_output, final_result_output]
        )
        
    return demo

def main():
    """主函数"""
    # 检查必要的环境变量
    required_vars = ["API_KEY", "BASE_URL"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ 缺少必要的环境变量: {', '.join(missing_vars)}")
        print("请在.env文件中设置这些变量")
        return
    
    # 创建并启动界面
    demo = create_research_interface()
    
    print("🚀 启动Open Deep Research界面...")
    print("📝 确保已设置好环境变量: API_KEY, BASE_URL, SERPAPI_API_KEY")
    print("✅ ANSI终端模拟功能已启用，将在浏览器中显示完整的终端效果")
    print("🎨 支持颜色、粗体、下划线等终端格式")
    
    demo.launch(
        server_name="0.0.0.0",  # 允许外部访问
        server_port=6789,       # 默认端口
        show_error=True,        # 显示错误信息
        share=False,            # 设为True可生成公开链接
        inbrowser=True          # 自动打开浏览器
    )

if __name__ == "__main__":
    main()
