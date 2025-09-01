#!/usr/bin/env python
# coding=utf-8

# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import glob
import fnmatch
from pathlib import Path
from typing import Optional

from .tools import Tool


class ListDirectoryTool(Tool):
    """
    列出目录中的文件和子目录。
    
    此工具可以列出指定目录中的所有文件和子目录，支持可选的文件过滤模式。
    """
    
    name = "list_directory"
    description = "列出指定目录中的文件和子目录。可以选择性地应用文件名过滤模式。"
    inputs = {
        "directory_path": {
            "type": "string",
            "description": "要列出内容的目录路径。如果为空，则使用当前目录。"
        },
        "pattern": {
            "type": "string", 
            "description": "可选的文件名过滤模式（如 '*.py' 或 'test_*'）。如果为空，列出所有文件。",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, directory_path: str, pattern: Optional[str] = None) -> str:
        try:
            # 如果目录路径为空，使用当前目录
            if not directory_path:
                directory_path = "."
            
            # 检查目录是否存在
            path = Path(directory_path)
            if not path.exists():
                return f"错误：目录 '{directory_path}' 不存在。"
            
            if not path.is_dir():
                return f"错误：'{directory_path}' 不是一个目录。"
            
            # 获取目录内容
            items = []
            try:
                for item in path.iterdir():
                    # 如果有过滤模式，应用过滤
                    if pattern and not fnmatch.fnmatch(item.name, pattern):
                        continue
                    
                    if item.is_dir():
                        items.append(f"📁 {item.name}/")
                    else:
                        # 获取文件大小
                        try:
                            size = item.stat().st_size
                            size_str = self._format_size(size)
                            items.append(f"📄 {item.name} ({size_str})")
                        except (OSError, PermissionError):
                            items.append(f"📄 {item.name}")
            
            except PermissionError:
                return f"错误：没有权限访问目录 '{directory_path}'。"
            
            if not items:
                if pattern:
                    return f"目录 '{directory_path}' 中没有匹配模式 '{pattern}' 的文件或目录。"
                else:
                    return f"目录 '{directory_path}' 为空。"
            
            # 排序并格式化输出
            items.sort()
            result = f"目录 '{directory_path}' 的内容:\n"
            if pattern:
                result += f"（过滤模式：{pattern}）\n"
            result += "\n".join(items)
            result += f"\n\n总计：{len(items)} 项"
            
            return result
            
        except Exception as e:
            return f"列出目录时发生错误：{str(e)}"
    
    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"


class ReadFileTool(Tool):
    """
    读取文件内容。
    
    此工具可以读取指定文件的内容并返回为字符串。支持文本文件的读取。
    """
    
    name = "read_file"
    description = "读取指定文件的内容并返回为字符串。"
    inputs = {
        "file_path": {
            "type": "string",
            "description": "要读取的文件路径。"
        },
        "encoding": {
            "type": "string",
            "description": "文件编码格式，默认为 'utf-8'。",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, file_path: str, encoding: Optional[str] = None) -> str:
        try:
            if not file_path:
                return "错误：文件路径不能为空。"
            
            # 默认编码
            if encoding is None:
                encoding = "utf-8"
            
            # 检查文件是否存在
            path = Path(file_path)
            if not path.exists():
                return f"错误：文件 '{file_path}' 不存在。"
            
            if not path.is_file():
                return f"错误：'{file_path}' 不是一个文件。"
            
            # 读取文件内容
            try:
                with open(path, 'r', encoding=encoding) as file:
                    content = file.read()
                
                # 获取文件信息
                file_size = path.stat().st_size
                line_count = content.count('\n') + 1 if content else 0
                
                result = f"文件：{file_path}\n"
                result += f"大小：{self._format_size(file_size)}\n"
                result += f"行数：{line_count}\n"
                result += f"编码：{encoding}\n"
                result += "=" * 50 + "\n"
                result += content
                
                return result
                
            except UnicodeDecodeError:
                return f"错误：无法使用 '{encoding}' 编码读取文件。文件可能是二进制文件或使用不同的编码。"
            except PermissionError:
                return f"错误：没有权限读取文件 '{file_path}'。"
            
        except Exception as e:
            return f"读取文件时发生错误：{str(e)}"
    
    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"


class WriteFileTool(Tool):
    """
    写入内容到文件。
    
    此工具可以将指定内容写入文件。如果文件不存在则创建，如果存在则覆盖。
    """
    
    name = "write_file"
    description = "将指定内容写入文件。如果文件不存在则创建，如果存在则覆盖。"
    inputs = {
        "file_path": {
            "type": "string",
            "description": "要写入的文件路径。"
        },
        "content": {
            "type": "string",
            "description": "要写入文件的内容。"
        },
        "encoding": {
            "type": "string",
            "description": "文件编码格式，默认为 'utf-8'。",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, file_path: str, content: str, encoding: Optional[str] = None) -> str:
        try:
            if not file_path:
                return "错误：文件路径不能为空。"
            
            # 默认编码
            if encoding is None:
                encoding = "utf-8"
            
            path = Path(file_path)
            
            # 创建目录（如果不存在）
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            try:
                with open(path, 'w', encoding=encoding) as file:
                    file.write(content)
                
                # 获取写入后的文件信息
                file_size = path.stat().st_size
                line_count = content.count('\n') + 1 if content else 0
                
                result = f"成功写入文件：{file_path}\n"
                result += f"大小：{self._format_size(file_size)}\n"
                result += f"行数：{line_count}\n"
                result += f"编码：{encoding}"
                
                return result
                
            except PermissionError:
                return f"错误：没有权限写入文件 '{file_path}'。"
            except Exception as write_error:
                return f"写入文件时发生错误：{str(write_error)}"
            
        except Exception as e:
            return f"写入文件时发生错误：{str(e)}"
    
    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"


class FileSearchTool(Tool):
    """
    在指定目录中搜索文件。
    
    此工具可以根据文件名模式在目录中搜索文件，支持递归搜索子目录。
    """
    
    name = "search_files"
    description = "在指定目录中根据文件名模式搜索文件，支持递归搜索。"
    inputs = {
        "directory_path": {
            "type": "string", 
            "description": "要搜索的目录路径。如果为空，则使用当前目录。"
        },
        "pattern": {
            "type": "string",
            "description": "文件名搜索模式，支持通配符（如 '*.py', 'test_*.txt'）。"
        },
        "recursive": {
            "type": "boolean",
            "description": "是否递归搜索子目录，默认为 True。",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, directory_path: str, pattern: str, recursive: Optional[bool] = None) -> str:
        try:
            if not pattern:
                return "错误：搜索模式不能为空。"
            
            # 如果目录路径为空，使用当前目录
            if not directory_path:
                directory_path = "."
            
            # 默认递归搜索
            if recursive is None:
                recursive = True
            
            # 检查目录是否存在
            path = Path(directory_path)
            if not path.exists():
                return f"错误：目录 '{directory_path}' 不存在。"
            
            if not path.is_dir():
                return f"错误：'{directory_path}' 不是一个目录。"
            
            # 搜索文件
            found_files = []
            try:
                if recursive:
                    # 递归搜索
                    search_pattern = str(path / "**" / pattern)
                    found_files = glob.glob(search_pattern, recursive=True)
                else:
                    # 仅在当前目录搜索
                    search_pattern = str(path / pattern)
                    found_files = glob.glob(search_pattern)
                
                # 过滤出文件（排除目录）
                found_files = [f for f in found_files if Path(f).is_file()]
                
            except Exception as search_error:
                return f"搜索过程中发生错误：{str(search_error)}"
            
            if not found_files:
                search_type = "递归" if recursive else "非递归"
                return f"在目录 '{directory_path}' 中没有找到匹配模式 '{pattern}' 的文件（{search_type}搜索）。"
            
            # 格式化结果
            found_files.sort()
            result = f"在目录 '{directory_path}' 中找到 {len(found_files)} 个匹配 '{pattern}' 的文件"
            result += f"（{'递归' if recursive else '非递归'}搜索）:\n\n"
            
            for file_path in found_files:
                try:
                    file_size = Path(file_path).stat().st_size
                    size_str = self._format_size(file_size)
                    # 使用相对路径显示
                    rel_path = os.path.relpath(file_path, directory_path)
                    result += f"📄 {rel_path} ({size_str})\n"
                except (OSError, PermissionError):
                    rel_path = os.path.relpath(file_path, directory_path)
                    result += f"📄 {rel_path}\n"
            
            return result
            
        except Exception as e:
            return f"搜索文件时发生错误：{str(e)}"
    
    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"


class FileContentSearchTool(Tool):
    """
    在文件中搜索指定内容。
    
    此工具可以在指定文件或目录中的文件内容中搜索指定的文本模式。
    """
    
    name = "search_file_content"
    description = "在文件内容中搜索指定的文本模式，支持在单个文件或目录中的多个文件中搜索。"
    inputs = {
        "search_path": {
            "type": "string",
            "description": "要搜索的文件路径或目录路径。"
        },
        "search_text": {
            "type": "string", 
            "description": "要搜索的文本内容。"
        },
        "file_pattern": {
            "type": "string",
            "description": "当搜索目录时，指定要搜索的文件类型模式（如 '*.py', '*.txt'）。如果为空则搜索所有文本文件。",
            "nullable": True
        },
        "case_sensitive": {
            "type": "boolean",
            "description": "是否区分大小写，默认为 False。",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, search_path: str, search_text: str, file_pattern: Optional[str] = None, case_sensitive: Optional[bool] = None) -> str:
        try:
            if not search_path:
                return "错误：搜索路径不能为空。"
            
            if not search_text:
                return "错误：搜索文本不能为空。"
            
            # 默认不区分大小写
            if case_sensitive is None:
                case_sensitive = False
            
            path = Path(search_path)
            if not path.exists():
                return f"错误：路径 '{search_path}' 不存在。"
            
            results = []
            
            if path.is_file():
                # 搜索单个文件
                result = self._search_in_file(path, search_text, case_sensitive)
                if result:
                    results.extend(result)
            elif path.is_dir():
                # 搜索目录中的文件
                if file_pattern is None:
                    file_pattern = "*"
                
                # 获取匹配的文件
                search_pattern = str(path / "**" / file_pattern)
                files = glob.glob(search_pattern, recursive=True)
                files = [f for f in files if Path(f).is_file()]
                
                for file_path in files:
                    file_results = self._search_in_file(Path(file_path), search_text, case_sensitive)
                    if file_results:
                        results.extend(file_results)
            
            if not results:
                search_type = "区分大小写" if case_sensitive else "不区分大小写"
                if path.is_file():
                    return f"在文件 '{search_path}' 中没有找到 '{search_text}'（{search_type}）。"
                else:
                    pattern_info = f"，文件模式：{file_pattern}" if file_pattern and file_pattern != "*" else ""
                    return f"在目录 '{search_path}' 中没有找到 '{search_text}'（{search_type}{pattern_info}）。"
            
            # 格式化结果
            search_type = "区分大小写" if case_sensitive else "不区分大小写"
            result_text = f"搜索 '{search_text}'（{search_type}）的结果:\n\n"
            
            current_file = None
            for file_path, line_num, line_content in results:
                if file_path != current_file:
                    if current_file is not None:
                        result_text += "\n"
                    result_text += f"📄 {file_path}:\n"
                    current_file = file_path
                
                result_text += f"  行 {line_num}: {line_content.strip()}\n"
            
            result_text += f"\n总计找到 {len(results)} 处匹配。"
            return result_text
            
        except Exception as e:
            return f"搜索文件内容时发生错误：{str(e)}"
    
    def _search_in_file(self, file_path: Path, search_text: str, case_sensitive: bool) -> list:
        """在单个文件中搜索文本"""
        results = []
        try:
            # 尝试不同的编码
            encodings = ['utf-8', 'gbk', 'latin1']
            content = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as file:
                        content = file.readlines()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                # 无法读取文件，可能是二进制文件
                return results
            
            # 搜索文本
            search_lower = search_text.lower() if not case_sensitive else search_text
            
            for line_num, line in enumerate(content, 1):
                line_to_search = line if case_sensitive else line.lower()
                if search_lower in line_to_search:
                    results.append((str(file_path), line_num, line))
        
        except (PermissionError, OSError):
            # 跳过无法访问的文件
            pass
        
        return results


__all__ = [
    "ListDirectoryTool",
    "ReadFileTool", 
    "WriteFileTool",
    "FileSearchTool",
    "FileContentSearchTool",
]
