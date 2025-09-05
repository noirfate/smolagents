#!/usr/bin/env python3
"""
Chrome浏览器网页内容提取测试脚本

用法:
    python test_chrome_browser.py <url>
    
示例:
    python test_chrome_browser.py https://www.baidu.com
    python test_chrome_browser.py https://github.com/huggingface/smolagents
"""

import argparse
import time
import random

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.common.exceptions import WebDriverException, TimeoutException

class BrowserTester:
    """Chrome浏览器测试类"""
    
    def __init__(self):
        self.driver = None
    
    def create_driver(self):
        """创建Chrome WebDriver实例"""
        print("🚀 正在启动Chrome浏览器...")
        try:
            chrome_options = ChromeOptions()
            chrome_options.add_argument("--headless")  # 无头模式
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(30)
            
            print("✅ Chrome浏览器启动成功")
            return True
            
        except Exception as e:
            print(f"❌ 启动Chrome浏览器失败: {e}")
            print("\n💡 解决方案:")
            print("1. 确保已安装Chrome浏览器")
            print("2. 确保已安装ChromeDriver: pip install chromedriver-autoinstaller")
            print("3. 或者下载ChromeDriver: https://chromedriver.chromium.org/")
            return False
    
    def simulate_human_behavior(self):
        """模拟人类行为"""
        try:
            print("🤖 模拟人类行为...")
            # 简单的滚动行为
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(1)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
        except Exception as e:
            print(f"⚠️ 模拟人类行为时出错: {e}")
    
    def get_page_content(self, url: str, timeout: int = 10):
        """获取网页内容"""
        if not self.driver:
            if not self.create_driver():
                return None, None
        
        print(f"🌐 正在访问: {url}")
        
        try:
            # 访问页面
            self.driver.get(url)
            
            # 等待页面加载
            self.driver.implicitly_wait(timeout)
            
            # 模拟人类行为
            self.simulate_human_behavior()
            
            # 获取页面信息
            title = self.driver.title or "无标题"
            current_url = self.driver.current_url
            
            # 获取页面文本内容
            text_content = self.driver.execute_script("""
                return document.body.innerText;
            """)
            
            print(f"📄 页面标题: {title}")
            print(f"🔗 最终URL: {current_url}")
            print(f"📊 文本长度: {len(text_content)} 字符")
            
            return title, text_content
            
        except TimeoutException:
            print(f"⏰ 页面加载超时: {url}")
            return None, f"页面加载超时: {url}"
            
        except WebDriverException as e:
            print(f"❌ 浏览器错误: {str(e)}")
            return None, f"浏览器错误: {str(e)}"
            
        except Exception as e:
            print(f"❌ 未知错误: {str(e)}")
            return None, f"未知错误: {str(e)}"
    
    def close(self):
        """关闭浏览器"""
        if self.driver:
            try:
                print("🔄 正在关闭浏览器...")
                self.driver.quit()
                print("✅ 浏览器已关闭")
            except:
                print("⚠️ 关闭浏览器时出现错误（可忽略）")
            finally:
                self.driver = None


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Chrome浏览器网页内容提取测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
    python test_chrome_browser.py https://www.baidu.com
    python test_chrome_browser.py https://github.com/huggingface/smolagents
    python test_chrome_browser.py https://docs.python.org/3/
        """
    )
    
    parser.add_argument(
        "url", 
        type=str, 
        help="要测试的网页URL"
    )
    
    parser.add_argument(
        "--timeout", 
        type=int, 
        default=10,
        help="页面加载超时时间（秒），默认10秒"
    )
    
    args = parser.parse_args()
    
    # 检查URL格式
    if not args.url.startswith(('http://', 'https://')):
        print("❌ URL必须以http://或https://开头")
        return 1
    
    print("=" * 60)
    print("🧪 Chrome浏览器网页内容提取测试")
    print("=" * 60)
    
    tester = BrowserTester()
    
    try:
        # 提取网页内容
        title, text_content = tester.get_page_content(args.url, args.timeout)
        
        if text_content is None:
            print("❌ 内容提取失败")
            return 1
        
        print("\n" + "=" * 40)
        print("📋 提取结果")
        print("=" * 40)
        print(text_content)
        
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断测试")
        return 1
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        return 1
    finally:
        tester.close()
    
    return 0


if __name__ == "__main__":
    exit(main())
