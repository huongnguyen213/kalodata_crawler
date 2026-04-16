import yaml
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

from utils import (
    load_cookies_from_json,
    extract_table_to_markdown,
    build_js_fast_actions,
    build_js_slow_motion_actions
)


class KalodataCrawler:
    """Crawler class cho Kalodata product page"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Khởi tạo crawler với config file
        
        Args:
            config_path: Đường dẫn file config.yaml
        """
        self.config = self._load_config(config_path)
        self.crawler = None
        
    def _load_config(self, config_path: str) -> dict:
        """Load và merge config từ YAML file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f)
            
            return user_config
        except yaml.YAMLError as e:
            print(f"⚠️ Lỗi parse config YAML: {e}, dùng default config")
            return user_config
    
    def _build_browser_config(self) -> BrowserConfig:
        """Build BrowserConfig từ config"""
        browser_cfg = self.config["browser"]
        cookies = load_cookies_from_json(self.config["target"]["cookie_file"])
        
        return BrowserConfig(
            headless=browser_cfg.get("headless", False),
            viewport_width=browser_cfg.get("viewport_width", 1920),
            viewport_height=browser_cfg.get("viewport_height", 1080),
            user_agent=browser_cfg.get("user_agent", ""),
            cookies=cookies if cookies else None
        )
    
    def _build_crawler_config(self, js_code: str) -> CrawlerRunConfig:
        """Build CrawlerRunConfig từ config"""
        crawler_cfg = self.config["crawler"]
        
        # Map cache_mode string sang enum
        cache_modes = {
            "bypass": CacheMode.BYPASS,
            "enabled": CacheMode.ENABLED,
            "disabled": CacheMode.DISABLED
        }
        cache_mode = cache_modes.get(crawler_cfg.get("cache_mode", "bypass"), CacheMode.BYPASS)
        
        return CrawlerRunConfig(
            cache_mode=cache_mode,
            wait_for=crawler_cfg.get("wait_for", "tr.ant-table-row-level-0"),
            page_timeout=crawler_cfg.get("page_timeout", 240000),
            js_code=js_code,
            js_only=False,
            remove_overlay_elements=crawler_cfg.get("remove_overlay_elements", True)
        )
    
    def _build_js_code(self) -> str:
        """Build JS code dựa trên js_mode trong config"""
        js_mode = self.config.get("js_mode", "slow_motion")
        filter_cfg = self.config.get("filter", {})
        
        if js_mode == "fast":
            return build_js_fast_actions(
                tab_key=filter_cfg.get("tab_key", "-3"),
                tab_selector=filter_cfg.get("tab_selector", "#filter-tabs-tiktokfilter-drag-tabs-container"),
                sort_column=filter_cfg.get("sort_column", "Item Sold"),
                sort_delay=filter_cfg.get("sort_delay", 1500)
            )
        else:  # slow_motion
            return build_js_slow_motion_actions(self.config)
    
    def _print_debug_info(self, soup: BeautifulSoup):
        """In debug info về trạng thái page sau crawl"""
        # Check active tab
        active_tab = soup.select_one('.ant-tabs-tab-active .ant-tabs-tab-btn')
        if active_tab:
            print(f"📌 Tab active: {active_tab.get_text(strip=True)}")
        
        # Check sort status
        sort_col = self.config["filter"].get("sort_column", "Item Sold")
        sort_th = soup.select_one(f'th.ant-table-cell:-soup-contains("{sort_col}")')
        if sort_th:
            if sort_th.select_one('.ant-table-column-sorter-down.active'):
                print("📊 Sorted: descending")
            elif sort_th.select_one('.ant-table-column-sorter-up.active'):
                print("📊 Sorted: ascending")
    
    def _save_output(self, content: str, output_path: str):
        """Lưu output ra file, tạo thư mục nếu cần"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        print(f"✅ Đã lưu: {output_path}")
    
    def _print_preview(self, content: str):
        """In preview của output nếu cấu hình cho phép"""
        output_cfg = self.config.get("output", {})
        if not output_cfg.get("include_preview", True):
            return
        
        preview_len = output_cfg.get("preview_length", 400)
        print(f"\n📄 Preview ({preview_len} ký tự đầu):")
        print("-" * 50)
        print(content[:preview_len].strip())
        print("-" * 50)
    
    async def crawl(self) -> Optional[str]:
        """
        Chạy crawl chính
        
        Returns:
            str: Markdown content nếu thành công, None nếu lỗi
        """
        target = self.config["target"]
        
        # Build configs
        browser_cfg = self._build_browser_config()
        js_code = self._build_js_code()
        crawler_cfg = self._build_crawler_config(js_code)
        
        print(f"🚀 Crawl: {target['url']}")
        print(f"🎯 Filter: {self.config['filter'].get('tab_key')} | Sort: {self.config['filter'].get('sort_column')}")
        print(f"⚡ Mode: {self.config.get('js_mode', 'slow_motion')}")
        
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await crawler.arun(url=target["url"], config=crawler_cfg)
            
            if not result.success or not result.html:
                print(f"❌ Lỗi crawl: {result.error_message or 'Không có dữ liệu'}")
                return None
            
            # Parse và extract
            soup = BeautifulSoup(result.html, 'html.parser')
            self._print_debug_info(soup)
            
            markdown_content = extract_table_to_markdown(soup)
            
            # Save output
            self._save_output(markdown_content, target["output_file"])
            
            # Stats
            img_count = markdown_content.count("![img](")
            row_count = len([
                r for r in markdown_content.split('\n') 
                if r.strip().startswith('|') and '---' not in r
            ])
            
            print(f"📏 Kích thước: {len(markdown_content)} ký tự")
            print(f"🖼️  Số ảnh: {img_count} | 📋 Số hàng: {max(0, row_count - 2)}")
            
            # Preview
            self._print_preview(markdown_content)
            
            return markdown_content
    
    async def __aenter__(self):
        """Context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.crawler:
            await self.crawler.close()