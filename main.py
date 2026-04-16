import sys
import argparse
import asyncio
from pathlib import Path

from crawler import KalodataCrawler


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Kalodata Product Crawler - Extract TikTok Shop data to Markdown"
    )
    parser.add_argument(
        "-c", "--config",
        type=str,
        default="config.yaml",
        help="Đường dẫn file config YAML (default: config.yaml)"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Ghi đè output file path từ config"
    )
    parser.add_argument(
        "-f", "--fast",
        action="store_true",
        help="Chế độ fast: không highlight, chạy nhanh hơn"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Bật verbose logging"
    )
    return parser.parse_args()


async def main():
    """Main entry point"""
    args = parse_args()
    
    # Print header
    print("=" * 60)
    print("KALODATA PRODUCT CRAWLER")
    print("=" * 60)
    
    # Check cookie file exists
    from utils import load_cookies_from_json
    # Load config tạm để check cookie
    import yaml
    with open(args.config, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    cookie_file = config.get("target", {}).get("cookie_file", "cookie.json")
    
    if not Path(cookie_file).exists():
        print(f"Không tìm thấy cookie file: {cookie_file}")
        print("Hướng dẫn: Export cookie từ Chrome DevTools → Application → Cookies")
        return 1
    
    # Initialize crawler
    crawler = KalodataCrawler(config_path=args.config)
    
    # Override config nếu có args
    if args.output:
        crawler.config["target"]["output_file"] = args.output
    if args.fast:
        crawler.config["js_mode"] = "fast"
        print("Chế độ FAST enabled")
    
    # Run crawl
    try:
        result = await crawler.crawl()
        
        if result:
            print("\nCrawl hoàn thành!")
            return 0
        else:
            print("\n Crawl thất bại")
            return 1
            
    except KeyboardInterrupt:
        print("\n  Dừng bởi người dùng")
        return 130
    except Exception as e:
        print(f"\n Lỗi không mong đợi: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)