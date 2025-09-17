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
    
    此工具可以读取指定文件的内容并返回为字符串。支持文本文件的读取，并可以限制读取的行数。
    """
    
    name = "read_file"
    description = "读取指定文件的内容并返回为字符串。支持限制读取的行数以避免读取过大文件。"
    inputs = {
        "file_path": {
            "type": "string",
            "description": "要读取的文件路径。"
        },
        "encoding": {
            "type": "string",
            "description": "文件编码格式，默认为 'utf-8'。",
            "nullable": True
        },
        "max_lines": {
            "type": "integer",
            "description": "最大读取行数，默认为无限制。设置此参数可以防止读取过大的文件。",
            "nullable": True
        },
        "start_line": {
            "type": "integer", 
            "description": "开始读取的行号（从1开始），默认为1。",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, file_path: str, encoding: Optional[str] = None, max_lines: Optional[int] = None, start_line: Optional[int] = None) -> str:
        try:
            if not file_path:
                return "错误：文件路径不能为空。"
            
            # 默认编码
            if encoding is None:
                encoding = "utf-8"
            
            # 默认开始行号
            if start_line is None:
                start_line = 1
            elif start_line < 1:
                return "错误：开始行号必须大于等于1。"
            
            # 检查文件是否存在
            path = Path(file_path)
            if not path.exists():
                return f"错误：文件 '{file_path}' 不存在。"
            
            if not path.is_file():
                return f"错误：'{file_path}' 不是一个文件。"
            
            # 读取文件内容
            try:
                with open(path, 'r', encoding=encoding) as file:
                    lines = file.readlines()
                
                # 获取文件基本信息
                file_size = path.stat().st_size
                total_lines = len(lines)
                
                # 检查开始行号是否有效
                if start_line > total_lines:
                    return f"错误：开始行号 {start_line} 超出文件总行数 {total_lines}。"
                
                # 计算实际读取的行数范围
                start_idx = start_line - 1  # 转换为0基索引
                if max_lines is None:
                    end_idx = total_lines
                    selected_lines = lines[start_idx:]
                else:
                    end_idx = min(start_idx + max_lines, total_lines)
                    selected_lines = lines[start_idx:end_idx]
                
                # 构建内容
                content = ''.join(selected_lines)
                actual_lines_read = len(selected_lines)
                
                # 构建结果
                result = f"文件：{file_path}\n"
                result += f"大小：{self._format_size(file_size)}\n"
                result += f"总行数：{total_lines}\n"
                result += f"读取范围：第 {start_line} 行到第 {start_line + actual_lines_read - 1} 行\n"
                result += f"读取行数：{actual_lines_read}\n"
                result += f"编码：{encoding}\n"
                result += f"文件内容：\n"
                
                content = ''.join(selected_lines)
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


class EditFileTool(Tool):
    """
    编辑文件内容。
    
    此工具通过查找和替换的方式编辑文件内容。只需要指定原始内容和替换内容，工具会自动找到匹配的内容并替换。
    """
    
    name = "edit_file"
    description = "通过内容匹配的方式编辑文件，将指定的原始内容替换为新内容。"
    inputs = {
        "file_path": {
            "type": "string",
            "description": "要编辑的文件路径。"
        },
        "old_content": {
            "type": "string",
            "description": "要被替换的原始内容。必须完全匹配文件中的内容（包括所有空白字符、缩进、换行符等）。如果为空字符串则创建新文件。"
        },
        "new_content": {
            "type": "string",
            "description": "替换后的新内容。确保结果正确且符合语言规范。"
        },
        "expected_replacements": {
            "type": "integer",
            "description": "期望的替换次数，默认为1。用于验证替换操作是否按预期执行。",
            "nullable": True
        },
        "encoding": {
            "type": "string",
            "description": "文件编码格式，默认为 'utf-8'。",
            "nullable": True
        }
    }
    output_type = "string"
    
    def forward(self, file_path: str, old_content: str, new_content: str, 
                expected_replacements: Optional[int] = None, encoding: Optional[str] = None) -> str:
        try:
            if not file_path:
                return "错误：文件路径不能为空。"
            
            # 默认编码和期望替换次数
            if encoding is None:
                encoding = "utf-8"
            if expected_replacements is None:
                expected_replacements = 1
            
            path = Path(file_path)
            
            # 处理创建新文件的情况
            if old_content == "":
                if path.exists():
                    return f"错误：尝试创建已存在的文件 '{file_path}'。使用非空的old_content来编辑现有文件。"
                
                # 创建新文件
                try:
                    # 确保父目录存在
                    path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(path, 'w', encoding=encoding) as file:
                        file.write(new_content)
                    
                    file_size = path.stat().st_size
                    new_lines = new_content.count('\n') + 1 if new_content else 0
                    
                    result = f"✅ 成功创建新文件：{file_path}\n"
                    result += f"编码：{encoding}\n"
                    result += f"行数：{new_lines}\n"
                    result += f"文件大小：{self._format_size(file_size)}\n"
                    result += "=" * 50 + "\n"
                    result += f"文件内容：\n{new_content}"
                    
                    return result
                    
                except PermissionError:
                    return f"错误：没有权限创建文件 '{file_path}'。"
                except Exception as create_error:
                    return f"创建文件时发生错误：{str(create_error)}"
            
            # 编辑现有文件
            if not path.exists():
                return f"错误：文件 '{file_path}' 不存在。使用空的old_content来创建新文件。"
            
            if not path.is_file():
                return f"错误：'{file_path}' 不是一个文件。"
            
            # 读取文件内容
            try:
                with open(path, 'r', encoding=encoding) as file:
                    content = file.read()
                
                # 标准化换行符为LF
                content = content.replace('\r\n', '\n')
                
                # 检查原始内容是否存在
                if old_content not in content:
                    return f"错误：在文件中未找到指定的原始内容。请使用ReadFileTool验证文件内容。\n查找内容: {repr(old_content)}"
                
                # 计算替换次数
                replace_count = content.count(old_content)
                
                # 验证期望的替换次数
                if replace_count != expected_replacements:
                    occurrence_term = "次" if expected_replacements == 1 else "次"
                    return f"错误：期望替换 {expected_replacements} {occurrence_term}，但找到 {replace_count} {occurrence_term}匹配项。"
                
                # 检查是否没有实际变更
                if old_content == new_content:
                    return f"警告：原始内容和新内容相同，无需变更。"
                
                # 执行替换
                updated_content = content.replace(old_content, new_content)
                
                # 写入修改后的内容
                with open(path, 'w', encoding=encoding) as file:
                    file.write(updated_content)
                
                # 获取文件信息
                original_size = len(content.encode(encoding))
                new_size = path.stat().st_size
                original_lines = content.count('\n') + 1 if content else 0
                new_lines = updated_content.count('\n') + 1 if updated_content else 0
                
                # 生成diff显示
                diff_content = self._generate_diff(content, updated_content, file_path)
                
                # 构建结果
                result = f"✅ 文件编辑成功：{file_path}\n"
                result += f"操作：内容替换\n"
                result += f"编码：{encoding}\n"
                result += f"替换次数：{replace_count}\n"
                result += f"原行数：{original_lines}\n"
                result += f"新行数：{new_lines}\n"
                result += f"文件大小：{self._format_size(original_size)} → {self._format_size(new_size)}\n"
                result += "=" * 50 + "\n"
                result += f"变更详情（diff）：\n{diff_content}"
                
                return result
                
            except UnicodeDecodeError:
                return f"错误：无法使用 '{encoding}' 编码读取文件。文件可能是二进制文件或使用不同的编码。"
            except PermissionError:
                return f"错误：没有权限编辑文件 '{file_path}'。"
            
        except Exception as e:
            return f"编辑文件时发生错误：{str(e)}"
    
    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"
    
    def _generate_diff(self, original_content: str, updated_content: str, file_path: str) -> str:
        """生成diff格式的变更内容"""
        import difflib
        from datetime import datetime
        
        # 将内容按行分割
        original_lines = original_content.splitlines(keepends=True)
        updated_lines = updated_content.splitlines(keepends=True)
        
        # 生成unified diff
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        diff_lines = list(difflib.unified_diff(
            original_lines,
            updated_lines,
            fromfile=f"{file_path} (原始)",
            tofile=f"{file_path} (修改后)",
            fromfiledate=timestamp,
            tofiledate=timestamp,
            lineterm=""
        ))
        
        # 如果没有差异，返回提示信息
        if not diff_lines:
            return "无变更内容"
        
        # 返回完整的diff内容
        diff_content = "".join(diff_lines)
        
        return diff_content


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
    在文件或目录中搜索包含指定内容的文件，支持通配符匹配，不支持递归搜索子目录。
    
    此工具可以在指定文件或目录中的文件内容中搜索指定的文本模式，支持使用通配符进行模式匹配。
    """
    
    name = "search_file_content"
    description = "在文件内容中搜索指定的文本模式，支持通配符匹配和在单个文件或目录中的多个文件中搜索。"
    inputs = {
        "search_path": {
            "type": "string",
            "description": "要搜索的文件路径或目录路径。"
        },
        "search_text": {
            "type": "string", 
            "description": "要搜索的文本内容或模式。支持通配符：* 匹配任意字符序列，? 匹配单个字符。"
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
            
            # 自动检测是否包含通配符
            has_wildcards = '*' in search_text or '?' in search_text
            
            path = Path(search_path)
            if not path.exists():
                return f"错误：路径 '{search_path}' 不存在。"
            
            results = []
            
            if path.is_file():
                # 搜索单个文件
                result = self._search_in_file(path, search_text, case_sensitive, has_wildcards)
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
                    file_results = self._search_in_file(Path(file_path), search_text, case_sensitive, has_wildcards)
                    if file_results:
                        results.extend(file_results)
            
            search_type = "区分大小写" if case_sensitive else "不区分大小写"
            wildcard_info = "，通配符模式" if has_wildcards else ""

            if not results:
                if path.is_file():
                    return f"在文件 '{search_path}' 中没有找到 '{search_text}'（{search_type}{wildcard_info}）。"
                else:
                    pattern_info = f"，文件模式：{file_pattern}" if file_pattern and file_pattern != "*" else ""
                    return f"在目录 '{search_path}' 中没有找到 '{search_text}'（{search_type}{wildcard_info}{pattern_info}）。"
            
            result_text = f"搜索 '{search_text}'（{search_type}{wildcard_info}）的结果:\n\n"
            
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
    
    def _search_in_file(self, file_path: Path, search_text: str, case_sensitive: bool, has_wildcards: bool) -> list:
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
            if has_wildcards:
                # 使用fnmatch进行通配符匹配
                search_pattern = search_text if case_sensitive else search_text.lower()
                
                for line_num, line in enumerate(content, 1):
                    line_to_search = line if case_sensitive else line.lower()
                    if fnmatch.fnmatch(line_to_search.rstrip('\n\r'), search_pattern):
                        results.append((str(file_path), line_num, line))
            else:
                # 使用普通字符串包含匹配
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
    "EditFileTool",
    "FileSearchTool",
    "FileContentSearchTool",
]
