"""
Shell Tools for smolagents

This module provides shell command execution tools that work across different operating systems.
Supports both Windows and Linux/Unix systems with proper error handling and security considerations.
"""

import subprocess
import sys
import os
import platform
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from .tools import Tool

__all__ = [
    "ExecuteCommandTool",
    "GetSystemInfoTool", 
    "CommandOutputManager",
    "MultiCommandManager",
    "CommandPageUpTool",
    "CommandPageDownTool",
    "GetCommandOutputTool",
    "ListCommandsTool",
    "ClearCommandTool",
    "SearchCommandTool",
    "SearchAllCommandsTool",
    "ShellTools",
]


class CommandOutputManager:
    """命令输出分页管理器，支持多命令并发管理"""
    
    def __init__(self, viewport_size: int = 20480):  # 20KB per page
        self.viewport_size = viewport_size
        self.command_output: str = ""
        self.command_info: str = ""
        self.command_id: str = ""
        self.viewport_current_page = 0
        self.viewport_pages: List[Tuple[int, int]] = []
        
    def set_output(self, command_id: str, command_output: str, command_info: str = ""):
        """设置命令输出内容并分页"""
        self.command_id = command_id
        self.command_output = command_output
        self.command_info = command_info
        self.viewport_current_page = 0
        self._split_pages()
        
    def _split_pages(self) -> None:
        """将输出内容分割成页面"""
        if len(self.command_output) == 0:
            self.viewport_pages = [(0, 0)]
            return
            
        self.viewport_pages = []
        start_idx = 0
        while start_idx < len(self.command_output):
            end_idx = min(start_idx + self.viewport_size, len(self.command_output))
            # 调整到在换行符处结束，避免截断行
            while (end_idx < len(self.command_output) and 
                   self.command_output[end_idx - 1] not in ["\n", "\r"]):
                end_idx += 1
            self.viewport_pages.append((start_idx, end_idx))
            start_idx = end_idx
    
    @property
    def viewport(self) -> str:
        """返回当前页面的内容"""
        if not self.viewport_pages:
            return ""
        bounds = self.viewport_pages[self.viewport_current_page]
        return self.command_output[bounds[0]:bounds[1]]
    
    @property
    def full_output(self) -> str:
        """返回完整的输出内容"""
        return self.command_output
        
    def page_down(self) -> None:
        """向下翻页"""
        self.viewport_current_page = min(self.viewport_current_page + 1, len(self.viewport_pages) - 1)
        
    def page_up(self) -> None:
        """向上翻页"""
        self.viewport_current_page = max(self.viewport_current_page - 1, 0)
        
    def get_state(self) -> str:
        """获取当前状态信息"""
        current_page = self.viewport_current_page + 1
        total_pages = len(self.viewport_pages)
        
        header = f"命令ID: {self.command_id}\n"
        header += self.command_info
        if not header.endswith('\n'):
            header += '\n'
        header += f"分页显示: 第 {current_page}/{total_pages} 页"
        if total_pages > 1:
            header += f" (使用 cmd_page_up/cmd_page_down 翻页，使用 search_cmd 搜索内容)"
        header += "\n" + "=" * 50 + "\n"
        
        return header + self.viewport
        
    def search_content(self, keyword: str, context_lines: int = 1000) -> List[Dict[str, any]]:
        """在命令输出中搜索关键词"""
        if not keyword.strip():
            return []
            
        results = []
        lines = self.command_output.split('\n')
        keyword_lower = keyword.lower()
        
        for i, line in enumerate(lines):
            if keyword_lower in line.lower():
                # 计算上下文范围
                start_line = max(0, i - context_lines)
                end_line = min(len(lines), i + context_lines + 1)
                
                # 提取上下文
                context = lines[start_line:end_line]
                
                # 高亮匹配的关键词
                highlighted_context = []
                for j, context_line in enumerate(context):
                    actual_line_num = start_line + j
                    if actual_line_num == i:  # 匹配行
                        # 高亮关键词
                        highlighted_line = context_line
                        # 简单的大小写不敏感替换
                        import re
                        highlighted_line = re.sub(
                            re.escape(keyword), 
                            f"**{keyword}**", 
                            highlighted_line, 
                            flags=re.IGNORECASE
                        )
                        highlighted_context.append(f">>> {highlighted_line}")
                    else:
                        highlighted_context.append(f"    {context_line}")
                
                results.append({
                    'line_number': i + 1,
                    'matched_line': line,
                    'context': '\n'.join(highlighted_context),
                    'start_line': start_line + 1,
                    'end_line': end_line
                })
                
        return results


class MultiCommandManager:
    """多命令输出管理器，支持异步和并发命令管理"""
    
    def __init__(self):
        self.commands: Dict[str, CommandOutputManager] = {}
        self.current_command_id: Optional[str] = None
        
    def add_command(self, command_id: str, command_output: str, command_info: str = "", viewport_size: int = 20480) -> str:
        """添加新命令输出"""
        manager = CommandOutputManager(viewport_size)
        manager.set_output(command_id, command_output, command_info)
        self.commands[command_id] = manager
        self.current_command_id = command_id
        return manager.get_state()
        
    def get_command_state(self, command_id: str) -> str:
        """获取指定命令的当前状态"""
        if command_id not in self.commands:
            return f"错误：找不到命令ID '{command_id}'"
        self.current_command_id = command_id
        return self.commands[command_id].get_state()
        
    def page_up(self, command_id: Optional[str] = None) -> str:
        """向上翻页"""
        target_id = command_id or self.current_command_id
        if not target_id or target_id not in self.commands:
            return f"错误：找不到命令ID '{target_id}'"
        self.commands[target_id].page_up()
        self.current_command_id = target_id
        return self.commands[target_id].get_state()
        
    def page_down(self, command_id: Optional[str] = None) -> str:
        """向下翻页"""
        target_id = command_id or self.current_command_id
        if not target_id or target_id not in self.commands:
            return f"错误：找不到命令ID '{target_id}'"
        self.commands[target_id].page_down()
        self.current_command_id = target_id
        return self.commands[target_id].get_state()
        
    def list_commands(self) -> str:
        """列出所有命令"""
        if not self.commands:
            return "当前没有保存的命令输出"
        
        result = "已保存的命令输出：\n"
        for cmd_id, manager in self.commands.items():
            pages = len(manager.viewport_pages)
            current = "← 当前" if cmd_id == self.current_command_id else ""
            result += f"- {cmd_id}: {pages}页 {current}\n"
        result += f"\n使用 get_cmd_output(command_id='xxx') 查看特定命令输出"
        return result
        
    def clear_command(self, command_id: str) -> str:
        """清除指定命令"""
        if command_id not in self.commands:
            return f"错误：找不到命令ID '{command_id}'"
        del self.commands[command_id]
        if self.current_command_id == command_id:
            self.current_command_id = None
        return f"已清除命令 '{command_id}'"
        
    def search_in_command(self, command_id: str, keyword: str, context_lines: int = 1000) -> str:
        """在指定命令输出中搜索关键词"""
        if command_id not in self.commands:
            return f"错误：找不到命令ID '{command_id}'"
            
        results = self.commands[command_id].search_content(keyword, context_lines)
        
        if not results:
            return f"在命令 '{command_id}' 中未找到关键词 '{keyword}'"
            
        output = f"在命令 '{command_id}' 中找到 {len(results)} 个匹配项，关键词: '{keyword}'\n"
        output += "=" * 60 + "\n\n"
        
        for i, result in enumerate(results, 1):
            output += f"匹配 {i}: 第 {result['line_number']} 行\n"
            output += f"{result['context']}\n"
            output += "-" * 40 + "\n\n"
            
        return output.rstrip()
        
    def search_in_all_commands(self, keyword: str, context_lines: int = 1000) -> str:
        """在所有命令输出中搜索关键词"""
        if not self.commands:
            return "当前没有保存的命令输出"
            
        all_results = {}
        total_matches = 0
        
        for cmd_id, manager in self.commands.items():
            results = manager.search_content(keyword, context_lines)
            if results:
                all_results[cmd_id] = results
                total_matches += len(results)
                
        if not all_results:
            return f"在所有命令中未找到关键词 '{keyword}'"
            
        output = f"在 {len(all_results)} 个命令中找到 {total_matches} 个匹配项，关键词: '{keyword}'\n"
        output += "=" * 60 + "\n\n"
        
        for cmd_id, results in all_results.items():
            output += f"命令: {cmd_id} ({len(results)} 个匹配)\n"
            output += "-" * 30 + "\n"
            
            for i, result in enumerate(results, 1):
                output += f"  匹配 {i}: 第 {result['line_number']} 行\n"
                # 缩进上下文内容
                indented_context = '\n'.join(f"  {line}" for line in result['context'].split('\n'))
                output += f"{indented_context}\n\n"
                
            output += "\n"
            
        return output.rstrip()


# 全局多命令管理器实例
_global_multi_manager = MultiCommandManager()


class CommandPageUpTool(Tool):
    """命令输出向上翻页工具"""
    name = "cmd_page_up"
    description = "在命令输出中向上翻页，显示前一页内容"
    inputs = {
        "command_id": {
            "type": "string",
            "description": "命令ID，如果不提供则使用当前命令",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, command_id: Optional[str] = None) -> str:
        return _global_multi_manager.page_up(command_id)


class CommandPageDownTool(Tool):
    """命令输出向下翻页工具"""
    name = "cmd_page_down" 
    description = "在命令输出中向下翻页，显示后一页内容"
    inputs = {
        "command_id": {
            "type": "string",
            "description": "命令ID，如果不提供则使用当前命令",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, command_id: Optional[str] = None) -> str:
        return _global_multi_manager.page_down(command_id)


class GetCommandOutputTool(Tool):
    """获取指定命令输出工具"""
    name = "get_cmd_output"
    description = "获取指定命令ID的输出内容（切换到该命令的当前页面）"
    inputs = {
        "command_id": {
            "type": "string", 
            "description": "要查看的命令ID"
        }
    }
    output_type = "string"
    
    def forward(self, command_id: str) -> str:
        return _global_multi_manager.get_command_state(command_id)


class ListCommandsTool(Tool):
    """列出所有保存的命令工具"""
    name = "list_commands"
    description = "列出所有已保存的命令输出及其分页信息"
    inputs = {}
    output_type = "string"
    
    def forward(self) -> str:
        return _global_multi_manager.list_commands()


class ClearCommandTool(Tool):
    """清除指定命令输出工具"""
    name = "clear_cmd"
    description = "清除指定命令ID的输出内容，释放内存"
    inputs = {
        "command_id": {
            "type": "string",
            "description": "要清除的命令ID"
        }
    }
    output_type = "string"
    
    def forward(self, command_id: str) -> str:
        return _global_multi_manager.clear_command(command_id)


class SearchCommandTool(Tool):
    """在指定命令输出中搜索关键词工具"""
    name = "search_cmd"
    description = "在指定命令的输出中搜索关键词，返回匹配行及上下文"
    inputs = {
        "command_id": {
            "type": "string",
            "description": "要搜索的命令ID"
        },
        "keyword": {
            "type": "string", 
            "description": "要搜索的关键词"
        },
        "context_lines": {
            "type": "integer",
            "description": "显示匹配行前后的上下文行数，默认为1000行",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, command_id: str, keyword: str, context_lines: Optional[int] = None) -> str:
        if context_lines is None:
            context_lines = 1000
        return _global_multi_manager.search_in_command(command_id, keyword, context_lines)


class SearchAllCommandsTool(Tool):
    """在所有命令输出中搜索关键词工具"""
    name = "search_all_cmds"
    description = "在所有已保存的命令输出中搜索关键词，返回所有匹配结果"
    inputs = {
        "keyword": {
            "type": "string",
            "description": "要搜索的关键词"
        },
        "context_lines": {
            "type": "integer",
            "description": "显示匹配行前后的上下文行数，默认为1000行",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, keyword: str, context_lines: Optional[int] = None) -> str:
        if context_lines is None:
            context_lines = 1000
        return _global_multi_manager.search_in_all_commands(keyword, context_lines)


class ExecuteCommandTool(Tool):
    """
    执行系统命令的工具。
    
    支持Windows和Linux/Unix系统，提供安全的命令执行环境，包括超时控制、工作目录设置等功能。
    输出超过页面大小时自动分页显示。
    """
    
    name = "exec_cmd"
    description = "执行系统命令并返回结果。支持Windows和Linux/Unix系统。输出超过页面大小时自动分页显示。"
    
    def __init__(self):
        super().__init__()
        self.default_page_size = 20480  # 默认20KB页面大小
    inputs = {
        "command": {
            "type": "string",
            "description": "要执行的命令。在Windows上使用cmd语法，在Linux/Unix上使用bash语法。"
        },
        "working_directory": {
            "type": "string", 
            "description": "命令执行的工作目录，默认为当前目录。",
            "nullable": True
        },
        "timeout": {
            "type": "integer",
            "description": "命令超时时间（秒），默认为60秒。设置为0表示无超时限制。",
            "nullable": True
        },
        "env_vars": {
            "type": "object",
            "description": "额外的环境变量字典，将合并到当前环境变量中。",
            "nullable": True
        },
        "page_size": {
            "type": "integer", 
            "description": "分页大小（字节），默认20480字节(20KB)。输出超过此大小时自动分页。",
            "nullable": True
        },
        "command_id": {
            "type": "string",
            "description": "自定义命令ID，用于后续引用。如果不提供，将自动生成基于时间戳的ID。",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, command: str, working_directory: Optional[str] = None, 
                timeout: Optional[int] = None, env_vars: Optional[Dict[str, str]] = None,
                page_size: Optional[int] = None, command_id: Optional[str] = None) -> str:
        try:
            if not command or not command.strip():
                return "错误：命令不能为空。"
            
            # 设置默认值
            if timeout is None:
                timeout = 60
            if page_size is None:
                page_size = self.default_page_size  # 使用实例的默认页面大小
            if command_id is None:
                import uuid
                import datetime
                timestamp = datetime.datetime.now().strftime("%H%M%S")
                command_id = f"cmd_{timestamp}_{str(uuid.uuid4())[:8]}"
            
            # 验证工作目录
            if working_directory:
                work_dir = Path(working_directory)
                if not work_dir.exists():
                    return f"错误：工作目录不存在：{working_directory}"
                if not work_dir.is_dir():
                    return f"错误：指定的路径不是目录：{working_directory}"
            else:
                working_directory = os.getcwd()
            
            # 准备环境变量
            env = os.environ.copy()
            if env_vars:
                env.update(env_vars)
            
            # 执行命令
            import time
            start_time = time.time()
            
            # 在Windows上设置正确的编码
            encoding = 'utf-8' if platform.system() != 'Windows' else 'gbk'
            errors = 'replace'  # 替换无法解码的字符
            
            try:
                result = subprocess.run(
                    command,
                    cwd=working_directory,
                    capture_output=True,
                    text=True,
                    encoding=encoding,
                    errors=errors,
                    timeout=timeout if timeout > 0 else None,
                    env=env,
                    shell=True
                )
            except UnicodeDecodeError:
                # 如果编码失败，尝试使用UTF-8
                result = subprocess.run(
                    command,
                    cwd=working_directory,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=timeout if timeout > 0 else None,
                    env=env,
                    shell=True
                )
            
            end_time = time.time()
            execution_time = round(end_time - start_time, 2)
            
            # 构建结果
            status = "成功" if result.returncode == 0 else "失败"
            command_info = f"✅ 命令执行{status}\n"
            command_info += f"命令：{command}\n"
            command_info += f"工作目录：{working_directory}\n"
            command_info += f"执行时间：{execution_time}秒\n"
            command_info += f"退出码：{result.returncode}\n"
            command_info += f"系统：{platform.system()} {platform.release()}\n"
            
            # 构建输出内容
            output_content = ""
            if result.stdout:
                output_content += "标准输出：\n"
                output_content += result.stdout
                if not result.stdout.endswith('\n'):
                    output_content += '\n'
            
            if result.stderr:
                output_content += "标准错误：\n" 
                output_content += result.stderr
                if not result.stderr.endswith('\n'):
                    output_content += '\n'
            
            if not result.stdout and not result.stderr:
                output_content += "无输出内容\n"
            
            # 自动分页逻辑：输出超过页面大小时自动分页
            global _global_multi_manager
            if len(output_content) > page_size:
                # 输出超过页面大小，自动分页显示
                return _global_multi_manager.add_command(command_id, output_content, command_info, page_size)
            else:
                # 输出未超过页面大小，完整显示，但仍然保存到管理器中以供后续引用
                _global_multi_manager.add_command(command_id, output_content, command_info, len(output_content))
                return f"命令ID: {command_id}\n" + command_info + "=" * 50 + "\n" + output_content
            
        except subprocess.TimeoutExpired:
            return f"错误：命令执行超时（{timeout}秒）：{command}"
        except FileNotFoundError:
            return f"错误：找不到命令或程序：{command}"
        except PermissionError:
            return f"错误：没有权限执行命令：{command}"
        except Exception as e:
            return f"执行命令时发生错误：{str(e)}"


class GetSystemInfoTool(Tool):
    """
    获取系统信息的工具。
    
    提供操作系统、硬件、Python环境等详细信息。
    """
    
    name = "sys_info"
    description = "获取系统信息，包括操作系统、硬件配置、Python环境等。"
    inputs = {
        "info_type": {
            "type": "string",
            "description": "信息类型：'all'(全部)、'os'(操作系统)、'hardware'(硬件)、'python'(Python环境)、'network'(网络)。默认为'all'。",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, info_type: Optional[str] = None) -> str:
        try:
            if info_type is None:
                info_type = "all"
            
            info_type = info_type.lower()
            
            result = "🖥️ 系统信息\n"
            result += "=" * 50 + "\n"
            
            # 操作系统信息
            if info_type in ["all", "os"]:
                result += "📋 操作系统信息：\n"
                result += f"系统：{platform.system()}\n"
                result += f"版本：{platform.release()}\n"
                result += f"详细版本：{platform.version()}\n"
                result += f"架构：{platform.machine()}\n"
                result += f"处理器：{platform.processor()}\n"
                result += f"主机名：{platform.node()}\n"
                result += "\n"
            
            # 硬件信息
            if info_type in ["all", "hardware"]:
                result += "⚙️ 硬件信息：\n"
                try:
                    import psutil
                    # CPU信息
                    result += f"CPU核心数：{psutil.cpu_count(logical=False)} 物理核心，{psutil.cpu_count(logical=True)} 逻辑核心\n"
                    result += f"CPU使用率：{psutil.cpu_percent(interval=1)}%\n"
                    
                    # 内存信息
                    memory = psutil.virtual_memory()
                    result += f"内存：{self._format_bytes(memory.total)} 总计，{self._format_bytes(memory.available)} 可用\n"
                    result += f"内存使用率：{memory.percent}%\n"
                    
                    # 磁盘信息
                    disk = psutil.disk_usage('/' if platform.system() != 'Windows' else 'C:')
                    result += f"磁盘：{self._format_bytes(disk.total)} 总计，{self._format_bytes(disk.free)} 可用\n"
                    result += f"磁盘使用率：{round((disk.used / disk.total) * 100, 1)}%\n"
                    
                except ImportError:
                    result += "需要安装 psutil 库来获取详细硬件信息\n"
                result += "\n"
            
            # Python环境信息
            if info_type in ["all", "python"]:
                result += "🐍 Python环境：\n"
                result += f"Python版本：{sys.version}\n"
                result += f"Python路径：{sys.executable}\n"
                result += f"当前工作目录：{os.getcwd()}\n"
                result += f"Python路径：{':'.join(sys.path[:3])}...\n"
                result += "\n"
            
            # 网络信息
            if info_type in ["all", "network"]:
                result += "🌐 网络信息：\n"
                try:
                    import socket
                    hostname = socket.gethostname()
                    local_ip = socket.gethostbyname(hostname)
                    result += f"主机名：{hostname}\n"
                    result += f"本地IP：{local_ip}\n"
                except Exception as e:
                    result += f"无法获取网络信息：{str(e)}\n"
                result += "\n"
            
            return result.rstrip()
            
        except Exception as e:
            return f"获取系统信息时发生错误：{str(e)}"
    
    def _format_bytes(self, bytes_value: int) -> str:
        """格式化字节数"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024
        return f"{bytes_value:.1f} PB"


class ShellTools:
    """
    Shell工具集合管理器
    
    提供一套完整的系统命令执行、分页管理和搜索工具。
    """
    
    def __init__(
        self,
        default_page_size: int = 20480,  # 20KB
        include_system_info: bool = True
    ):
        """
        初始化Shell工具集合
        
        Args:
            default_page_size: 默认分页大小（字节），超过此大小自动分页
            include_system_info: 是否包含系统信息工具
        """
        self.default_page_size = default_page_size
        self.include_system_info = include_system_info
        self._tools = None
    
    @property
    def tools(self) -> List[Tool]:
        """获取所有shell工具的列表"""
        if self._tools is None:
            self._tools = self._create_tools()
        return self._tools
    
    def _create_tools(self) -> List[Tool]:
        """创建所有shell工具"""
        tools = []
        
        # 核心命令执行工具（使用自定义页面大小）
        execute_tool = ExecuteCommandTool()
        execute_tool.default_page_size = self.default_page_size  # 设置默认页面大小
        tools.append(execute_tool)
        
        # 系统信息工具（可选）
        if self.include_system_info:
            tools.append(GetSystemInfoTool())
        
        # 分页和管理工具（始终包含，因为分页是自动的）
        tools.extend([
            CommandPageUpTool(),      # 向上翻页
            CommandPageDownTool(),    # 向下翻页
            GetCommandOutputTool(),   # 获取指定命令输出
            ListCommandsTool(),       # 列出所有命令
            ClearCommandTool(),       # 清除命令输出
            SearchCommandTool(),      # 搜索指定命令输出
            SearchAllCommandsTool(),  # 搜索所有命令输出
        ])
        
        return tools
    
    def get_command_manager(self) -> MultiCommandManager:
        """获取多命令管理器实例"""
        return _global_multi_manager
    
    def get_execute_tool(self) -> ExecuteCommandTool:
        """获取命令执行工具实例"""
        return ExecuteCommandTool()
    
    def get_system_info_tool(self) -> GetSystemInfoTool:
        """获取系统信息工具实例"""
        return GetSystemInfoTool()
    
    def __len__(self) -> int:
        """返回工具数量"""
        return len(self.tools)
    
    def __iter__(self):
        """支持迭代"""
        return iter(self.tools)
    
    def __getitem__(self, index):
        """支持索引访问"""
        return self.tools[index]
