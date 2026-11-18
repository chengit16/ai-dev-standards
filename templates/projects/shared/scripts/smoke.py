"""启动两个临时回环服务，检验实际页面入口、API 代理和失联响应。"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def ports() -> tuple[int, int]:
    """同时分配两个端口，减少竞争；实际启动仍需确认进程与探测结果。"""
    with socket.socket() as api, socket.socket() as web:
        for handle in (api, web):
            handle.bind(("127.0.0.1", 0))
        return api.getsockname()[1], web.getsockname()[1]


@contextmanager
def service(argv: list[str], cwd: Path, env: dict[str, str]):
    """单独管理本次启动的进程组，包括包管理器派生的服务。"""
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(
            argv, cwd=cwd, env=env, stdout=log, stderr=log, start_new_session=True
        )
        try:
            yield process
        except BaseException:
            log.seek(0)
            print(log.read().decode(errors="replace")[-4000:], file=sys.stderr)
            raise
        finally:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(process.pid, sig)
                    process.wait(timeout=3)
                except ProcessLookupError:
                    break
                except subprocess.TimeoutExpired:
                    continue


def wait(url: str, process: subprocess.Popen) -> bytes:
    """等待服务就绪，启动失败和端口竞争均返回明确失败。"""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"服务提前退出：{process.returncode}")
        try:
            with urlopen(url, timeout=1) as response:
                return response.read()
        except (URLError, TimeoutError):
            time.sleep(0.15)
    raise RuntimeError(f"等待服务超时：{url}")


def interrupted(signum: int, _frame: object) -> None:
    """让外层检查超时发出的终止信号经过服务清理流程。"""
    raise SystemExit(128 + signum)


def check(template: str) -> None:
    """使用生成项目自身的启动依赖，验证代理成功与后端关闭后的行为。"""
    root = Path(__file__).resolve().parents[1]
    api_port, web_port = ports()
    env = dict(os.environ, STARTER_API_PORT=str(api_port))
    api_url = f"http://127.0.0.1:{api_port}"
    web_url = f"http://127.0.0.1:{web_port}"
    backend = {
        "react-fastapi": [
            "uv",
            "run",
            "--no-sync",
            "uvicorn",
            "app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
        ],
        "react-nestjs": ["pnpm", "start"],
    }[template]
    with service(
        ["pnpm", "dev", "--port", str(web_port)],
        root / "apps/web",
        dict(env, STARTER_API_TARGET=api_url),
    ) as web:
        if b'id="root"' not in wait(web_url, web):
            raise RuntimeError("前端未返回应用入口")
        with service(backend, root / "apps/api", env) as api:
            if json.loads(wait(api_url + "/api/health", api)) != {"status": "ok"}:
                raise RuntimeError("API 健康响应不符合契约")
            if json.loads(wait(web_url + "/api/health", web)) != {"status": "ok"}:
                raise RuntimeError("前端代理返回的响应不符合契约")
        try:
            with urlopen(web_url + "/api/health", timeout=3):
                raise RuntimeError("后端关闭后代理仍返回成功")
        except HTTPError as error:
            if error.code < 500:
                raise
    print("页面入口、真实健康接口、开发代理及失联响应均通过")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"react-fastapi", "react-nestjs"}:
        raise SystemExit("用法：python3 scripts/smoke.py react-fastapi|react-nestjs")
    signal.signal(signal.SIGTERM, interrupted)
    check(sys.argv[1])
