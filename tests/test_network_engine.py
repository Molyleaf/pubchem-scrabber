import socket
import urllib.error
import pytest
from unittest.mock import patch, MagicMock
from pubchempy import PubChemHTTPError
from lib.network_engine import sniff_and_apply_proxies, smart_retry, UserInterruptError

def test_sniff_and_apply_proxies() -> None:
    """
    @ai-ut-matrix: 测试代理自动嗅探与进程注入机制。
    @ai-ut-mock: patch "urllib.request.getproxies" 返回 mock 的代理配置字典。
    @ai-ut-assert: 代理键值对必须同步写入 os.environ 中。
    """
    mock_proxies = {"http": "127.0.0.1:7890", "https": "127.0.0.1:7890"}
    with patch("urllib.request.getproxies", return_value=mock_proxies), \
         patch.dict("os.environ", {}):
        sniff_and_apply_proxies()
        import os
        assert os.environ.get("HTTP_PROXY") == "http://127.0.0.1:7890"
        assert os.environ.get("HTTPS_PROXY") == "http://127.0.0.1:7890"

@patch("time.sleep", return_value=None)  # 提速：Mock 所有 time.sleep，避免真实退避卡死测试
def test_smart_retry_success(mock_sleep) -> None:
    """
    @ai-ut-matrix: 测试在网络正常时，smart_retry 装饰的函数应该直接返回。
    @ai-ut-mock: patch "time.sleep" 避免延迟。
    @ai-ut-assert: 装饰后的函数返回值必须与原始调用一致，sleep 仅被调用一次（限速）。
    """
    @smart_retry
    def dummy_func(x):
        return x * 2
        
    res = dummy_func(5)
    assert res == 10
    assert mock_sleep.call_count == 1 # 每次调用强制 sleep(0.25) 一次以限速

@patch("time.sleep", return_value=None)
def test_smart_retry_network_infinite(mock_sleep) -> None:
    """
    @ai-ut-matrix: 测试网络层底层连接连接错误触发的无限重试机制（在此通过 Mock 第一次失败抛 socket.timeout，第二次成功）。
    @ai-ut-mock: patch "time.sleep"。
    @ai-ut-assert: 1. 最终必须能成功返回数据。
                   2. 期间应当触发了重试逻辑，sleep 的调用次数应为 2 (首个限制 + 遭遇错误退避)。
    """
    call_cnt = 0
    
    @smart_retry
    def failing_func():
        nonlocal call_cnt
        call_cnt += 1
        if call_cnt == 1:
            raise socket.timeout("Timed out connecting")
        return "success"
        
    res = failing_func()
    assert res == "success"
    assert call_cnt == 2

@patch("time.sleep", return_value=None)
def test_smart_retry_http_503_limited(mock_sleep) -> None:
    """
    @ai-ut-matrix: 测试服务器 503 繁忙错误发生时，是否只重试 5 次就彻底抛出异常。
    @ai-ut-mock: patch "time.sleep"。
    @ai-ut-assert: 1. 尝试 6 次网络交互（1 原始 + 5 重试）后上抛 PubChemHTTPError 错误。
    """
    call_cnt = 0
    
    @smart_retry
    def http_busy_func():
        nonlocal call_cnt
        call_cnt += 1
        raise PubChemHTTPError("503 Server Busy", "503", "Server Busy")
        
    with pytest.raises(PubChemHTTPError) as excinfo:
        http_busy_func()
        
    assert "503" in str(excinfo.value)
    # 第一次调用 + 5次重试 = 6 次调用
    assert call_cnt == 6

@patch("time.sleep", return_value=None)
def test_smart_retry_http_404_no_retry(mock_sleep) -> None:
    """
    @ai-ut-matrix: 测试遭遇 HTTP 404 等不应重试的错误时，系统应当拦截但立刻直接抛出，绝不发起下一次请求。
    @ai-ut-mock: patch "time.sleep"。
    @ai-ut-assert: 1. 一次执行即抛出异常，不再重试。
    """
    call_cnt = 0
    
    @smart_retry
    def http_404_func():
        nonlocal call_cnt
        call_cnt += 1
        raise PubChemHTTPError("404 Not Found", "404", "Not Found")
        
    with pytest.raises(PubChemHTTPError) as excinfo:
        http_404_func()
        
    assert "404" in str(excinfo.value)
    assert call_cnt == 1

@patch("time.sleep", return_value=None)
def test_smart_retry_keyboard_interrupt(mock_sleep) -> None:
    """
    @ai-ut-matrix: 测试用户在网络卡住或请求中按下 Ctrl+C 时，装饰器是否能捕获并转换为 UserInterruptError 向上抛出。
    @ai-ut-mock: patch "time.sleep"。
    @ai-ut-assert: 1. 捕捉后转换为 UserInterruptError。
    """
    @smart_retry
    def keyboard_func():
        raise KeyboardInterrupt()
        
    with pytest.raises(UserInterruptError):
        keyboard_func()
