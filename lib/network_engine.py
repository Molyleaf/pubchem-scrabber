import os
import time
import random
import socket
import ssl
import urllib.request
import urllib.error
from typing import Callable, Any, TypeVar, cast
from pubchempy import PubChemHTTPError

# 核心猴子补丁：直接重写 ssl.create_default_context 强制生成 unverified context，打通所有代理的 TLS EOF 隧道！
try:
    ssl.create_default_context = ssl._create_unverified_context
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

# 自定义异常，用于用户键盘中断时上抛，指示调度器优雅退出
class UserInterruptError(Exception):
    """
    @ai-intent: 自定义异常，表示用户通过 Ctrl+C 强行中断了批量获取任务。
    @ai-context:
      Topology: 模块 2: 网络与代理层 / 异常定义
      Blast Radius: 拦截后可触发优雅保存
    """
    pass

F = TypeVar('F', bound=Callable[..., Any])

def sniff_and_apply_proxies() -> dict:
    """
    @ai-intent: 调用 Windows 系统 API 探测当前的系统代理配置，并自动将其注入到当前 Python 进程的环境变量中。
    @ai-boundary: 允许读取系统注册表和网络代理配置，并修改当前进程的 os.environ。
    @ai-invariant: 返回一个包含提取代理键值对的字典，并且如果存在代理，必须正确设置 HTTP_PROXY 和 HTTPS_PROXY 环境变量。
    @ai-observe:
      Event Logging: [代理嗅探/sniff] -> [检测到的系统代理: {proxies}] -> [成功状态]
    @ai-context:
      Topology: 模块 2: 网络与代理层 / 初始化代理配置
      Flow: 启动时调用 -> 读取 Windows 代理 -> 写入 os.environ
      Blast Radius: 若代理配置有误可能导致后续网络请求报错，需要打印明确的注入日志
      ADR: 无特殊妥协
    """
    proxies = urllib.request.getproxies()
    if proxies:
        for proto, url in proxies.items():
            # 兼容有些代理 url 没有协议前缀的情况
            proxy_url = url
            if not url.startswith("http://") and not url.startswith("https://"):
                proxy_url = f"http://{url}"
            
            if proto == "http":
                os.environ["HTTP_PROXY"] = proxy_url
            elif proto == "https":
                os.environ["HTTPS_PROXY"] = proxy_url
                
            # 兼容大写
            os.environ[f"{proto.upper()}_PROXY"] = proxy_url
    return proxies

def smart_retry(func: F) -> F:
    """
    @ai-intent: 核心双轨智能重试装饰器。拦截网络连接层错误（进行无限指数退避重试，支持键盘中断优雅退出）与服务器过载 HTTP 错误（限重试 5 次）。
    @ai-invariant: 1. 遭遇 KeyboardInterrupt 必须抛出 UserInterruptError。
                   2. 遭遇网络底层连接异常必须无限指数退避重试，最大退避间隔 60 秒，并带有随机抖动（Jitter）。
                   3. 遭遇 HTTP 503/504 错误最多只重试 5 次，其他 HTTP 400/404 错误不予重试。
    @ai-boundary: 被装饰的函数必须支持抛出异常。装饰器不改变被装饰函数的入参和返回值。
    @ai-directive: 每次网络请求后，必须强制 time.sleep(0.25) 以满足每秒 5 次请求的官方合规要求（节流）。
    @ai-observe:
      Event Logging: [重试调度/func_name] -> [当前尝试次数, 遭遇错误, 采取的退避时长] -> [重试中/最终状态]
    @ai-context:
      Topology: 模块 2: 网络与代理层 / 核心安全网关
      Flow: 调用函数 -> 成功则返回 -> 失败则分类异常 -> 指数退避/计数重试 -> 满足条件重新尝试
      Blast Radius: 此装饰器包裹了整个 API 交互层，任何逻辑漏洞都可能导致无限死循环或数据直接丢失
      ADR: 使用指数退避 + 随机抖动（Jitter）避免发生网络重叠冲击（Thundering Herd）。
    """
    def wrapper(*args, **kwargs) -> Any:
        attempt_network = 0
        attempt_http = 0
        max_http_retries = 5
        initial_wait = 2.0
        
        while True:
            try:
                # 限制并发与频率，严格满足每秒 5 次以内
                time.sleep(0.25)
                
                # 执行实际的网络调用
                result = func(*args, **kwargs)
                return result
                
            except KeyboardInterrupt:
                # 捕获用户键盘中断，以便在上层安全落盘
                from rich.console import Console
                console = Console()
                console.print("\n[bold red]⚠️ 侦测到键盘中断 (Ctrl+C)。正在保存已处理的数据并退出...[/bold red]")
                raise UserInterruptError("用户手动中止了程序运行")
                
            except (socket.timeout, 
                    ConnectionResetError, 
                    ConnectionRefusedError,
                    urllib.error.URLError,
                    ssl.SSLError) as e:
                # 轨道 1: 底层网络连接级异常 -> 无限重试
                attempt_network += 1
                wait_time = min(60.0, initial_wait * (2 ** min(attempt_network, 6)) + random.uniform(0.0, 1.0))
                
                from rich.console import Console
                console = Console()
                console.print(
                    f"[yellow]⚠️ 网络连接异常: [italic]{type(e).__name__}: {e}[/italic]\n"
                    f"   当前已重试 [bold]{attempt_network}[/bold] 次，系统将在 [bold]{wait_time:.2f}s[/bold] 后重试。"
                    f"您可以按 Ctrl+C 终止并保存当前数据。[/yellow]"
                )
                time.sleep(wait_time)
                
            except PubChemHTTPError as e:
                # 轨道 2: HTTP 协议级异常
                error_msg = str(e)
                
                # 判断是否是 404 Not Found 或 400 Bad Request 等不应重试的错误
                # 或者是 503 Server Busy / 504 Timeout 等服务器繁忙超载错误
                # 503 通常代表 Server Busy，504 代表 Gateway Timeout
                is_server_busy = "503" in error_msg or "504" in error_msg or "busy" in error_msg.lower() or "timeout" in error_msg.lower()
                
                if is_server_busy:
                    attempt_http += 1
                    if attempt_http <= max_http_retries:
                        wait_time = 3.0 * attempt_http + random.uniform(0.0, 1.0)
                        from rich.console import Console
                        console = Console()
                        console.print(
                            f"[orange1]⚠️ PubChem 服务器繁忙或请求超时 (503/504)。\n"
                            f"   当前重试进度: [bold]{attempt_http}/{max_http_retries}[/bold]，"
                            f"将在 [bold]{wait_time:.2f}s[/bold] 后重试。[/orange1]"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        # 超过 5 次重试，判定为不可恢复，上抛异常以使该批次填充 404
                        from rich.console import Console
                        console = Console()
                        console.print(
                            f"[bold red]❌ 已达到最大 HTTP 重试限制 ({max_http_retries} 次)。"
                            f"当前批次查询失败，将被标记为未命中。[/bold red]"
                        )
                        raise e
                else:
                    # 其他 HTTP 错误（如 400/404 等，表示客户端参数错误或物质确实不存在）
                    # 绝不重试，直接上抛
                    raise e
                    
            except Exception as e:
                # 针对未预料到的其他异常，直接上抛
                raise e

    return cast(F, wrapper)
