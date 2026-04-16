import json
import re
import html
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup


def load_cookies_from_json(cookie_file: str) -> list[dict]:
    """
    Load và chuyển đổi cookie từ file JSON sang định dạng craw4ai/Playwright
    
    Args:
        cookie_file: Đường dẫn file JSON chứa cookies
        
    Returns:
        List[dict]: Danh sách cookies đã chuẩn hóa
    """
    try:
        with open(cookie_file, 'r', encoding='utf-8') as f:
            cookie_data = json.load(f)
        
        # Handle cả dict có key "cookies" hoặc list trực tiếp
        cookie_list = (
            cookie_data.get("cookies", cookie_data) 
            if isinstance(cookie_data, dict) 
            else cookie_data
        )
        
        cookies = []
        for c in cookie_list:
            # Chuẩn hóa sameSite
            same_site = c.get("sameSite", "unspecified")
            if same_site in ("unspecified", "no_restriction"):
                same_site = None
            elif same_site == "lax":
                same_site = "Lax"
            elif same_site == "strict":
                same_site = "Strict"
            
            cookie_dict = {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ""),
                "path": c.get("path", "/"),
                "httpOnly": c.get("httpOnly", False),
                "secure": c.get("secure", False),
            }
            
            if "expirationDate" in c and c["expirationDate"]:
                cookie_dict["expires"] = int(c["expirationDate"])
            if same_site:
                cookie_dict["sameSite"] = same_site
            
            cookies.append(cookie_dict)
        
        return cookies
        
    except FileNotFoundError:
        print(f"⚠️ Không tìm thấy file cookie: {cookie_file}")
        return []
    except json.JSONDecodeError as e:
        print(f"⚠️ Lỗi parse JSON cookie: {e}")
        return []
    except Exception as e:
        print(f"⚠️ Lỗi đọc cookie: {e}")
        return []


def extract_image_urls_from_style(style: str) -> list[str]:
    """
    Extract URLs từ CSS background-image style
    
    Args:
        style: Chuỗi CSS style chứa background-image
        
    Returns:
        List[str]: Danh sách URLs đã decode
    """
    urls = []
    # Regex match url(...), hỗ trợ có/không dấu nháy
    matches = re.findall(r'url\(\s*["\']?\s*(.*?)\s*["\']?\s*\)', style)
    
    for match in matches:
        # Decode HTML entities (&quot; -> ") và clean quotes
        url = html.unescape(match).strip().strip('"\'')
        if url.startswith(('http://', 'https://')):
            urls.append(url)
    
    return urls


def extract_table_to_markdown(soup: BeautifulSoup, table_selector: str = ".table-container") -> str:
    """
    Extract bảng sản phẩm từ HTML soup sang Markdown format, giữ link ảnh
    
    Args:
        soup: BeautifulSoup object chứa HTML đã parse
        table_selector: CSS selector để tìm table container
        
    Returns:
        str: Chuỗi Markdown của bảng
    """
    container = soup.select_one(table_selector)
    if not container:
        return "⚠️ Không tìm thấy table container"
    
    # === Extract Headers ===
    headers = []
    for th in container.select("thead th.ant-table-cell"):
        text = th.get_text(strip=True)
        if text:
            headers.append(text)
    
    if not headers:
        headers = [f"Col_{i+1}" for i in range(15)]  # Fallback default
    
    # === Extract Data Rows ===
    rows = []
    for tr in container.select("tr.ant-table-row-level-0"):
        cells = []
        for td in tr.select("td.ant-table-cell"):
            # 1. Extract images từ background-image
            img_links = []
            for div in td.select('div[style*="background-image"]'):
                style = div.get('style', '')
                urls = extract_image_urls_from_style(style)
                for url in urls:
                    img_links.append(f"![img]({url})")
            
            # 2. Extract text content
            text = " ".join(td.stripped_strings)
            
            # 3. Combine images + text
            cell_content = " ".join(img_links + ([text] if text else []))
            cells.append(cell_content)
        
        # Bỏ rows rỗng
        if any(c.strip() for c in cells):
            rows.append(cells)
    
    if not rows:
        return "⚠️ Không có dữ liệu hàng nào"
    
    # === Build Markdown Table ===
    num_cols = max(len(headers), max((len(r) for r in rows), default=0))
    
    # Pad headers và rows cho đủ số cột
    headers = headers[:num_cols] + [""] * (num_cols - len(headers))
    padded_rows = [r + [""] * (num_cols - len(r)) for r in rows]
    
    # Build lines
    md_lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * num_cols) + " |"
    ]
    for row in padded_rows:
        md_lines.append("| " + " | ".join(row) + " |")
    
    return "\n".join(md_lines)


def build_js_fast_actions(tab_key: str, tab_selector: str, sort_column: str, sort_delay: int) -> str:
    """
    Build JS code cho chế độ fast (click nhanh, không highlight)
    
    Returns:
        str: JavaScript code để inject vào browser
    """
    return f"""
    async () => {{
        console.log('🎯 Starting fast JS actions...');
        
        // 1. Click filter tab
        const affiliateTab = document.querySelector('{tab_selector} div[data-node-key="{tab_key}"]');
        if (affiliateTab) {{
            console.log('📌 Clicking filter tab...');
            affiliateTab.scrollIntoView({{ behavior: 'auto' }});
            await new Promise(r => setTimeout(r, 300));
            affiliateTab.click();
            
            // Wait for tab active + data fetch
            await new Promise((resolve) => {{
                const check = () => {{
                    if (affiliateTab.getAttribute('aria-selected') === 'true') {{
                        setTimeout(resolve, 2000);
                    }} else {{
                        setTimeout(check, 200);
                    }}
                }};
                check();
            }});
            console.log('✅ Tab clicked');
        }}
        
        // 2. Click sort column
        const sortHeader = Array.from(document.querySelectorAll('th.ant-table-cell'))
            .find(th => th.textContent && th.textContent.includes('{sort_column}'));
        
        if (sortHeader) {{
            console.log('📊 Clicking sort header...');
            sortHeader.scrollIntoView({{ behavior: 'auto' }});
            await new Promise(r => setTimeout(r, 300));
            sortHeader.click();
            
            // Wait for table reload
            await new Promise((resolve) => {{
                const check = () => {{
                    const rows = document.querySelectorAll('tr.ant-table-row-level-0');
                    if (rows.length > 0) {{
                        setTimeout(resolve, {sort_delay});
                    }} else {{
                        setTimeout(check, 200);
                    }}
                }};
                check();
            }});
            console.log('✅ Sorted');
        }}
        
        // 3. Final wait for lazy images
        await new Promise(r => setTimeout(r, 1000));
        console.log('🎉 Fast actions completed');
        return true;
    }}
    """


def build_js_slow_motion_actions(config: dict) -> str:
    """
    Build JS code cho chế độ slow-motion (có highlight, delay dài để quan sát)
    
    Args:
        config: Dict chứa cấu hình slow motion từ config.yaml
        
    Returns:
        str: JavaScript code để inject vào browser
    """
    sm = config.get('slow_motion', {})
    tab_key = config.get('filter', {}).get('tab_key', '-3')
    tab_selector = config.get('filter', {}).get('tab_selector', '#filter-tabs-tiktokfilter-drag-tabs-container')
    sort_column = config.get('filter', {}).get('sort_column', 'Item Sold')
    
    highlight_dur = sm.get('highlight_duration', 2000)
    scroll_delay = sm.get('scroll_delay', 1500)
    click_delay = sm.get('click_delay', 1000)
    reload_delay = sm.get('data_reload_delay', 3000)
    table_delay = sm.get('table_reload_delay', 4000)
    highlight_rows = sm.get('highlight_rows', 3)
    
    return f"""
    async () => {{
        // === Helper Functions ===
        const highlight = (el, duration = {highlight_dur}) => {{
            if (!el) return;
            const originalStyle = el.getAttribute('style') || '';
            el.setAttribute('data-original-style', originalStyle);
            el.style.transition = 'all 0.3s ease';
            el.style.border = '3px solid red !important';
            el.style.backgroundColor = 'rgba(255, 255, 0, 0.3) !important';
            el.style.zIndex = '9999';
            setTimeout(() => {{
                const orig = el.getAttribute('data-original-style');
                el.style.cssText = orig || '';
            }}, duration);
        }};

        const sleep = (ms, label) => {{
            console.log(`⏱️  [${{label}}] Chờ ${{ms/1000}}s...`);
            return new Promise(r => setTimeout(r, ms));
        }};

        console.log('🎬 BẮT ĐẦU DEMO SLOW-MOTION');
        await sleep(1000, 'Khởi động');

        // === STEP 1: Click Filter Tab ===
        console.log('🔹 Bước 1: Tìm filter tab...');
        await sleep({scroll_delay}, 'Tìm tab');
        
        const affiliateTab = document.querySelector('{tab_selector} div[data-node-key="{tab_key}"]');
        if (affiliateTab) {{
            console.log('✅ Tìm thấy tab, scroll vào view...');
            affiliateTab.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            await sleep({scroll_delay}, 'Scroll');
            
            console.log('🎯 Highlight tab...');
            highlight(affiliateTab, {highlight_dur});
            await sleep({highlight_dur}, 'Highlight');
            
            console.log('🖱️  Click tab...');
            affiliateTab.click();
            await sleep({click_delay}, 'Xử lý click');
            
            console.log('⏳ Chờ data reload...');
            await sleep({reload_delay}, 'Data reload');
            
            const isActive = affiliateTab.getAttribute('aria-selected') === 'true';
            console.log(isActive ? '✅ Tab active' : '⚠️ Tab chưa active');
        }} else {{
            console.error('❌ Không tìm thấy filter tab!');
        }}

        // === STEP 2: Click Sort Column ===
        console.log('\\n🔹 Bước 2: Tìm cột sort...');
        await sleep({scroll_delay}, 'Tìm header');
        
        const headers = document.querySelectorAll('th.ant-table-cell');
        const sortHeader = Array.from(headers).find(th => 
            th.innerText && th.innerText.includes('{sort_column}')
        );
        
        if (sortHeader) {{
            console.log('✅ Tìm thấy header, scroll...');
            sortHeader.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            await sleep({scroll_delay}, 'Scroll');
            
            console.log('🎯 Highlight header...');
            highlight(sortHeader, {highlight_dur});
            await sleep({highlight_dur}, 'Highlight');
            
            console.log('🖱️  Click header để sort...');
            sortHeader.click();
            await sleep({click_delay}, 'Xử lý click');
            
            console.log('⏳ Chờ table reload...');
            await sleep({table_delay}, 'Table reload');
            
            const sortIcon = sortHeader.querySelector('.ant-table-column-sorter-down.active, .ant-table-column-sorter-up.active');
            console.log(sortIcon ? '✅ Sort thành công' : '⚠️ Có thể chưa sort');
        }} else {{
            console.error('❌ Không tìm thấy cột sort!');
        }}

        // === STEP 3: Highlight data rows ===
        console.log('\\n🔹 Bước 3: Highlight các hàng đầu...');
        await sleep({click_delay}, 'Chuẩn bị');
        
        const firstRows = document.querySelectorAll('tr.ant-table-row-level-0');
        for (let i = 0; i < Math.min({highlight_rows}, firstRows.length); i++) {{
            console.log(`🎯 Highlight hàng #${{i+1}}...`);
            highlight(firstRows[i], {highlight_dur});
            await sleep({highlight_dur}, `Hàng #${{i+1}}`);
        }}

        console.log('\\n🎉 HOÀN TẤT DEMO SLOW-MOTION!');
        console.log('📊 Dữ liệu đã sẵn sàng.');
        return true;
    }}
    """