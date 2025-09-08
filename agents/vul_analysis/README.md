# 漏洞分析工作流 (Vulnerability Analysis Workflow)

这是一个基于smolagents的三阶段漏洞分析工作流，专门用于深入分析安全漏洞的技术细节、原理和利用方法。

## 🎯 功能特性

### 三阶段分析流程

1. **第一阶段：漏洞基础信息收集**
   - CVE编号和官方描述
   - CVSS评分和严重程度
   - 受影响组件和版本范围
   - 修复版本和补丁信息
   - 排查指导和检测方法

2. **第二阶段：漏洞原因分析**
   - 漏洞机制和根本原因
   - 代码层面的缺陷分析
   - 攻击向量和利用条件
   - 补丁代码对比分析
   - 缓解措施分析

3. **第三阶段：漏洞利用分析**
   - 漏洞环境Docker配置
   - 概念验证代码（POC）
   - 详细复现步骤指导

## 🚀 快速开始

### 环境准备

1. **克隆仓库**
```bash
git clone https://github.com/noirfate/smolagents
cd smolagents/
git checkout dev
```

2. **安装**
```bash
pip install -e .[docker,litellm,mcp,openai,telemetry,toolkit,vision]

pip install beautifulsoup4 google_search_results markdownify python-dotenv pypdf openpyxl pyPDF2 python-pptx mammoth pdfminer pdfminer.six puremagic pydub SpeechRecognition youtube_transcript_api ddgs
```

3. **安装其他可选依赖**
```bash
pip install selenium
wget -qO- https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-linux-signing-keyring.gpg

echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux-signing-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | tee /etc/apt/sources.list.d/google-chrome.list

apt update
apt install -y google-chrome-stable
```

### 环境变量配置

创建 `.env` 文件并配置必要的API密钥：

```bash
# LLM API配置
API_KEY=your_api_key_here
BASE_URL=your_base_url_here

# 可选：GitHub集成
GITHUB_TOKEN=your_github_token
```

## 📖 使用指南

### 基本用法

**完整分析：**
```bash
python run.py CVE-2024-1234
```

**指定模型和参数：**
```bash
python run.py CVE-2024-1234 --model-id gemini-2.5-pro --max-steps 30
```

**自定义输出目录：**
```bash
python run.py CVE-2024-1234 --output-dir custom_output
```

**启用监控：**
```bash
python run.py CVE-2024-1234 --enable-monitoring
```

**禁用无头浏览器：**
```bash
python run.py CVE-2024-1234 --disable-browser
```

### 命令行参数

| 参数 | 描述 | 默认值 |
|------|------|--------|
| `vulnerability_id` | 漏洞标识符（如CVE编号） | 必需 |
| `--model-id` | 使用的LLM模型 | `gemini-2.5-pro` |
| `--max-steps` | 每阶段最大执行步数 | `30` |
| `--stage` | 执行阶段（all/info/analysis/exploitation） | `all` |
| `--output-dir` | 输出目录 | `output` |
| `--enable-monitoring` | 启用Phoenix监控 | 禁用 |
| `--disable-browser` | 禁用高级浏览器功能 | 启用 |

## 📁 输出结果

工作流会在输出目录中创建以下文件：

```
output/
└── CVE-2024-1234/
    ├── stage1_info_CVE-2024-1234.md          # 第一阶段：基础信息
    ├── stage2_analysis_CVE-2024-1234.md      # 第二阶段：技术分析
    ├── stage3_exploitation_CVE-2024-1234.md  # 第三阶段：利用分析
    └── final_report_CVE-2024-1234.md         # 最终综合报告
```

## 🛠️ 技术架构

### 核心组件

- **主工作流** (`run.py`)：协调三个阶段的执行
- **信息收集器** (`scripts/vulnerability_info_collector.py`)：第一阶段agent
- **根因分析器** (`scripts/vulnerability_analysis.py`)：第二阶段agent
- **利用分析器** (`scripts/vulnerability_exploitation.py`)：第三阶段agent

### 依赖工具

- **GitHub工具**：利用`github mcp`进行代码搜索、仓库分析、提交历史分析等
- **浏览器工具**：利用selenium和无头浏览器更有效的提取网页内容
