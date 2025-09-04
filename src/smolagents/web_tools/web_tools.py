"""
WebTools class for smolagents

Provides a unified interface for all web browsing and search tools.
"""

import os
from typing import List, Optional, Dict, Any

from .text_inspector_tool import TextInspectorTool
from .text_web_browser import (
    ArchiveSearchTool,
    FinderTool,
    FindNextTool,
    PageDownTool,
    PageUpTool,
    SimpleTextBrowser,
    VisitTool,
)
from ..tools import Tool


class WebTools:
    """
    Web工具集合管理器
    
    提供一套完整的网页浏览、搜索和内容分析工具。
    """
    
    def __init__(
        self,
        model,
        text_limit: int = 100000,
        browser_config: Optional[Dict[str, Any]] = None,
        search_engine: str = "google",
    ):
        """
        初始化Web工具集合
        
        Args:
            model: 用于文本分析的模型实例
            text_limit: 文本分析的最大长度限制
            browser_config: 浏览器配置字典
            search_engine: 搜索引擎类型，支持 'google' 或 'duckduckgo'，默认为 'google'
        """
        self.model = model
        self.text_limit = text_limit
        self.search_engine = search_engine.lower()
        
        # 默认浏览器配置
        if browser_config is None:
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            browser_config = {
                "viewport_size": 1024 * 5,
                "downloads_folder": "downloads_folder",
                "request_kwargs": {
                    "headers": {"User-Agent": user_agent},
                    "timeout": 300,
                },
                "serpapi_key": os.getenv("SERPAPI_API_KEY"),
            }
            
            # 确保下载目录存在
            os.makedirs(f"./{browser_config['downloads_folder']}", exist_ok=True)
        
        self.browser_config = browser_config
        self.browser = SimpleTextBrowser(**browser_config)
        self._tools = None
    
    @property
    def tools(self) -> List[Tool]:
        """获取所有web工具的列表"""
        if self._tools is None:
            self._tools = self._create_tools()
        return self._tools
    
    def _create_tools(self) -> List[Tool]:
        """创建所有web工具"""
        tools = []
        
        # 添加搜索工具（根据搜索引擎类型选择）
        if self.search_engine == "google":
            from ..default_tools import GoogleSearchTool
            tools.append(GoogleSearchTool())
        elif self.search_engine == "duckduckgo":
            from ..default_tools import DuckDuckGoSearchTool
            tools.append(DuckDuckGoSearchTool())
        
        # 添加浏览器工具
        tools.extend([
            VisitTool(self.browser),
            PageUpTool(self.browser),
            PageDownTool(self.browser),
            FinderTool(self.browser),
            FindNextTool(self.browser),
            ArchiveSearchTool(self.browser),
            TextInspectorTool(self.model, self.text_limit),
        ])
        
        return tools
    
    def get_browser(self) -> SimpleTextBrowser:
        """获取浏览器实例"""
        return self.browser
    
    def get_text_inspector(self) -> TextInspectorTool:
        """获取文本检查工具实例"""
        return TextInspectorTool(self.model, self.text_limit)
    
    def __len__(self) -> int:
        """返回工具数量"""
        return len(self.tools)
    
    def __iter__(self):
        """支持迭代"""
        return iter(self.tools)
    
    def __getitem__(self, index):
        """支持索引访问"""
        return self.tools[index]
