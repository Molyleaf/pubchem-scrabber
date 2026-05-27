import sys
import os
import time
from typing import List

# 将当前运行目录加入 PYTHONPATH，确保 lib 模块可以顺利导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.cli_parser import parse_args, load_input_file
from lib.network_engine import sniff_and_apply_proxies, UserInterruptError
from lib.cache_manager import CacheManager
from lib.batch_dispatcher import dispatch_processing

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

# 初始化全局 Console
console = Console()

def print_banner() -> None:
    """
    @ai-intent: 打印管用的 CLI Banner，展示现代高品质终端质感，保证 Windows GBK 兼容。
    @ai-context:
      Topology: 主入口 app.py / UI 交互层
    """
    banner_text = Text()
    banner_text.append("[ PubChem bulk data retrieval client ]\n", style="bold cyan")
    banner_text.append("===================================================\n", style="blue")
    banner_text.append("   本地二级缓存 / 自动重试机制 / 输入输出行级对齐\n", style="italic magenta")
    banner_text.append("===================================================", style="blue")
    
    console.print(Panel(banner_text, expand=False, border_style="bold bright_cyan"))

def print_stats_table(total: int, cached: int, network: int, not_found: int, duration: float) -> None:
    """
    @ai-intent: 打印格式精美的彩色数据统计表格，WOW 用户。
    @ai-context:
      Topology: 主入口 app.py / 数据报表展示
    """
    table = Table(title="[Stats] 执行数据汇总", show_header=True, header_style="bold magenta")
    table.add_column("统计维度", style="cyan", width=25)
    table.add_column("值", style="yellow", justify="right", width=15)
    
    table.add_row("输入总行数 (Total Rows)", f"[bold cyan]{total}[/bold cyan]")
    table.add_row("本地缓存命中 (Cache Hits)", f"[bold green]{cached}[/bold green]")
    table.add_row("网络请求成功 (Network Success)", f"[bold blue]{network}[/bold blue]")
    table.add_row("未找到物质 (404 Not Found)", f"[bold red]{not_found}[/bold red]")
    table.add_row("总执行耗时 (Total Duration)", f"[bold pink1]{duration:.2f} 秒[/bold pink1]")
    
    console.print("\n")
    console.print(table)
    console.print("\n[bold green]处理完成，数据已成功导出并完成行级对齐。[/bold green]\n")

def main() -> None:
    """
    @ai-intent: 核心总控入口，串联参数解析、代理注入、数据加载、任务分发与 UI 渲染。
    @ai-boundary: 捕获全局异常与键盘中断，保证非零状态退出或安全优雅降级。
    @ai-observe:
      Event Logging: [全局主程序] -> [命令行参数] -> [执行成功/中途退出]
    @ai-context:
      Topology: 应用程序顶层总控
      Blast Radius: 此处是进程终点，异常未捕获将导致 traceback 裸露
    """
    print_banner()
    
    # 1. 解析参数
    try:
        args = parse_args()
    except SystemExit:
        return
        
    start_time = time.time()
    
    # 2. 检测 Windows 系统代理配置并应用
    with console.status("[bold blue][PROBE] 正在检测 Windows 系统代理配置...", spinner="dots"):
        proxies = sniff_and_apply_proxies()
        
    if proxies:
        console.print(f"[bold green][OK] 已检测到系统代理并应用：[/bold green] [italic]{proxies}[/italic]")
    else:
        console.print("[yellow][INFO] 未检测到系统代理，将使用直接连接。[/yellow]")
        
    # 3. 加载输入文件
    input_path = args.input
    header_strategy = args.header
    
    console.print(f"[bold blue][LOAD] 正在读取输入文件：[/bold blue] [italic]{os.path.basename(input_path)}[/italic] ...")
    try:
        sheets_results = load_input_file(input_path, header_strategy)
    except Exception as e:
        console.print(f"[bold red][ERROR] 无法读取输入文件: {e}[/bold red]")
        sys.exit(1)
        
    total_identifiers = sum(len(raw_ids) for _, _, raw_ids, _ in sheets_results)
    console.print(f"[bold green][OK] 读取完成。[/bold green] 共读取到 [bold cyan]{len(sheets_results)}[/bold cyan] 个工作表，累计 [bold cyan]{total_identifiers}[/bold cyan] 行待检索数据。")
    for name, df, raw_ids, has_header in sheets_results:
        console.print(f"   - 工作表 [bold magenta]{name}[/bold magenta] : [bold cyan]{len(raw_ids)}[/bold cyan] 行 (表头: {'已跳过' if has_header else '无表头'})")
    
    # 4. 初始化本地缓存管理器
    with console.status("[bold blue][CACHE] 正在加载本地化合物缓存...", spinner="dots"):
        cache_manager = CacheManager()
    
    comp_count = len(cache_manager.data.get("compounds", {}))
    idx_count = len(cache_manager.data.get("query_index", {}))
    console.print(
        f"[bold green][OK] 缓存已加载。[/bold green] 本地已缓存 [bold green]{comp_count}[/bold green] 种化合物，"
        f"包含 [bold green]{idx_count}[/bold green] 条二级映射关系。"
    )
    
    # 5. 启动批量调度与对齐处理器
    console.print("\n[bold cyan][START] 正在启动数据抓取与对齐...[/bold cyan]")
    
    interrupted = False
    stats = (total_identifiers, 0, 0, 0)
    
    try:
        with Progress(
            SpinnerColumn(spinner_name="simpleDotsScrolling"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40, complete_style="cyan", finished_style="green"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            
            task = progress.add_task("正在分配任务...", total=total_identifiers)
            
            last_logged_processed = -1
            
            def progress_callback(processed: int, total_pending: int, description: str) -> None:
                nonlocal last_logged_processed
                progress.update(
                    task, 
                    completed=processed, 
                    total=total_pending if total_pending > 0 else 1, 
                    description=description
                )
                
                percent = (processed / total_pending * 100) if total_pending > 0 else 0
                
                # 只有当进度发生变化，或者进行对齐和保存时才输出日志，避免过度刷新
                if processed != last_logged_processed or "正在对齐" in description or "正在写入" in description:
                    if "正在对齐" in description or "正在写入" in description:
                        console.print(f"[bold magenta][对齐与保存][/bold magenta] {description}")
                    else:
                        console.print(f"[bold cyan][进度: {processed}/{total_pending} ({percent:.1f}%)][/bold cyan] {description}")
                    last_logged_processed = processed
                
            stats = dispatch_processing(
                sheets_results=sheets_results,
                scope=args.scope,
                output_path=args.output,
                batch_size=args.batch,
                cache_manager=cache_manager,
                progress_callback=progress_callback
            )
            
    except UserInterruptError:
        interrupted = True
    except Exception as e:
        console.print(f"[bold red][ERROR] 执行失败: {e}[/bold red]")
        sys.exit(1)
        
    duration = time.time() - start_time
    
    if interrupted:
        console.print("\n[bold orange1][WARNING] 程序已被用户终止。已触发保护机制，保存当前已处理的数据。[/bold orange1]")
        console.print(f"[bold green][OK] 已成功获取并缓存的数据已保存至：[/bold green][italic]{args.output}[/italic]")
        
        # 重新统计中途断点导出的实际行数与 404 数
        actual_hits = 0
        actual_404 = 0
        for _, _, raw_ids, _ in sheets_results:
            for val in raw_ids:
                if not val:
                    actual_404 += 1
                    continue
                c = cache_manager.lookup(val)
                if c == "404 Not Found" or c is None:
                    actual_404 += 1
                else:
                    actual_hits += 1
        print_stats_table(total_identifiers, actual_hits, 0, actual_404, duration)
        sys.exit(0)
    else:
        # 成功完成
        total, cached, network, not_found = stats
        print_stats_table(total, cached, network, not_found, duration)

if __name__ == "__main__":
    main()
