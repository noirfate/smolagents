# Deep Research Agent

深度研究智能体 - 基于 [smolagents](https://github.com/huggingface/smolagents) 框架的增强版研究助手。本实现基于 `examples/open_deep_research` 进行了优化和扩展，提供了更强大的研究能力和更好的用户体验。

## 🌟 主要特性

### 核心功能
- 🌐 **智能网络搜索**: 使用Google搜索引擎进行准确的信息检索
- 🔥 **真实浏览器支持**: 集成Chrome浏览器执行JavaScript，获取纯文本内容
- 📊 **GitHub集成**: 深度集成GitHub工具，支持代码仓库分析和搜索
- 💻 **代码执行**: 专门的Python代码编写和执行环境
- 🤖 **多模型支持**: 支持多种主流AI模型
- 🧠 **智能记忆管理**: 基于Planning周期的记忆压缩技术
- 📱 **Web界面**: 提供美观的Gradio Web界面

### 技术特点
- **多Agent协作**: 搜索Agent、GitHub Agent和代码执行Agent协同工作
- **记忆压缩**: `MemoryCompressedCodeAgent` 和 `MemoryCompressedToolCallingAgent` 提供高效的记忆管理
- **目标漂移检测**: 集成 `GoalDriftCallback` 防止任务偏离

## 📋 系统要求

- Python 3.8+
- 足够的内存用于运行大型语言模型
- 稳定的网络连接用于API调用和网络搜索

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆仓库
git clone https://github.com/huggingface/smolagents.git
cd smolagents/agents/deep_research
```

### 2. 安装依赖

```bash
# 安装项目依赖
pip install -r requirements.txt

# 安装smolagents开发版本
pip install -e ../../.[dev]
```

### 3. 环境变量配置

创建 `.env` 文件并配置以下变量：

```bash
# 必需的API配置
API_KEY=your_api_key_here
BASE_URL=your_api_base_url_here

# 搜索引擎API密钥（二选一）
SERPAPI_API_KEY=your_serpapi_key_here
SERPER_API_KEY=your_serper_key_here

# GitHub集成（可选）
GITHUB_TOKEN=your_github_token_here

# 特定模型API密钥（根据使用的模型配置）
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
```

#### API密钥获取方式：
- **SerpApi**: [注册获取密钥](https://serpapi.com/users/sign_up)
- **Serper**: [注册获取密钥](https://serper.dev/signup)
- **GitHub Token**: [创建Personal Access Token](https://github.com/settings/tokens)
- **OpenAI**: [获取API密钥](https://platform.openai.com/signup)

### 4. 使用方式

#### 命令行模式

```bash
# 基础使用
python run.py "如何使用Python实现机器学习算法？"

# 指定模型
python run.py --model-id "gpt-4o" "分析最新的AI发展趋势"

# 自定义最大步数
python run.py --max-steps 30 "研究量子计算的最新进展"

# 启用监控
python run.py --enable-monitoring "深度分析区块链技术原理"
```

#### Web界面模式

```bash
# 启动Web界面
python app.py
```

然后在浏览器中访问 `http://localhost:6789`

## 🛠️ 配置选项

### 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `question` | str | - | 研究问题或任务描述 |
| `--model-id` | str | `gpt-5-chat` | 使用的AI模型 |
| `--max-steps` | int | `50` | Agent最大执行步数 |
| `--enable-monitoring` | bool | `False` | 启用Phoenix监控 |

### 支持的模型

- `o1` - OpenAI o1 模型
- `gpt-4o` - OpenAI GPT-4o
- `o3` - OpenAI o3 模型  
- `gpt-4.5-preview` - GPT-4.5预览版
- `claude-sonnet-4-20250514` - Claude Sonnet 4
- `ark-deepseek-r1-250528` - DeepSeek R1
- `gemini-2.5-pro` - Google Gemini 2.5 Pro

## 💡 使用示例

### 学术研究
```bash
python run.py "分析2024年自然语言处理领域的重要突破，包括技术原理和应用前景"
```

### 技术分析
```bash
python run.py "比较React和Vue.js框架的优缺点，并分析它们在GitHub上的活跃度"
```

### 市场调研
```bash
python run.py "研究电动汽车市场的发展趋势和主要厂商的技术路线"
```

### 代码分析
```bash
python run.py "分析TensorFlow和PyTorch的架构差异，并提供性能对比代码示例"
```

## 🔧 高级功能

### 记忆管理

本实现使用了记忆压缩技术，能够：
- 自动压缩长期对话历史
- 保留关键信息和上下文
- 优化Token使用效率
- 支持长时间研究任务

### 多Agent协作

系统包含三个专门的Agent：

1. **搜索Agent** (`search_agent`)
   - 负责网络搜索和信息收集
   - 支持复杂的搜索任务
   - 能够处理PDF、视频等多媒体内容

2. **GitHub Agent** (`github_agent`)
   - 专门处理GitHub相关任务
   - 支持代码仓库分析
   - 提供代码搜索和统计功能

3. **代码执行Agent** (`code_agent`)
   - 执行Python代码
   - 进行数据分析和可视化
   - 支持科学计算和机器学习任务

### 监控和调试

启用Phoenix监控可以：
- 跟踪LLM输入输出
- 监控Agent执行过程
- 分析性能和成本
- 调试复杂问题

## 📁 项目结构

```
agents/deep_research/
├── README.md              # 项目说明文档
├── requirements.txt       # Python依赖
├── run.py                # 命令行入口
├── app.py                # Web界面入口
├── downloads/            # 下载文件存储
├── downloads_folder/     # 临时下载目录
└── scripts/              # 工具脚本
    └── visual_qa.py      # 视觉问答功能
```

## 📄 许可证

本项目遵循与smolagents相同的许可证。

## 🙏 致谢

本项目基于 [smolagents](https://github.com/huggingface/smolagents) 框架开发，特别感谢Hugging Face团队的开源贡献。