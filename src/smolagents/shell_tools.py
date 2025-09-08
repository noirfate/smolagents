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
from typing import Optional, Dict
from .tools import Tool

__all__ = [
    "ExecuteCommandTool",
    "GetSystemInfoTool" 
]

class ExecuteCommandTool(Tool):
    """
    执行系统命令的工具。
    
    支持Windows和Linux/Unix系统，提供安全的命令执行环境，包括超时控制、工作目录设置等功能。
    """
    
    name = "exec_cmd"
    description = "执行系统命令并返回结果。支持Windows和Linux/Unix系统。"
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
        }
    }
    output_type = "string"
    
    def forward(self, command: str, working_directory: Optional[str] = None, 
                timeout: Optional[int] = None, env_vars: Optional[Dict[str, str]] = None) -> str:
        try:
            if not command or not command.strip():
                return "错误：命令不能为空。"
            
            # 设置默认值
            if timeout is None:
                timeout = 60
            
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
            result_text = f"✅ 命令执行{status}\n"
            result_text += f"命令：{command}\n"
            result_text += f"工作目录：{working_directory}\n"
            result_text += f"执行时间：{execution_time}秒\n"
            result_text += f"退出码：{result.returncode}\n"
            result_text += f"系统：{platform.system()} {platform.release()}\n"
            result_text += "=" * 50 + "\n"
            
            # 始终显示完整的命令输出
            if result.stdout:
                result_text += "标准输出：\n"
                result_text += result.stdout
                if not result.stdout.endswith('\n'):
                    result_text += '\n'
            
            if result.stderr:
                result_text += "标准错误：\n" 
                result_text += result.stderr
                if not result.stderr.endswith('\n'):
                    result_text += '\n'
            
            if not result.stdout and not result.stderr:
                result_text += "无输出内容\n"
            
            return result_text
            
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
