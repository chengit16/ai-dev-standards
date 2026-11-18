"""从明确的 Git 提交构建可校验的单文件工具包，不读取工作区改动。"""

from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from bootstrap.model import BootstrapError, digest
from lifecycle.model import STAMP, bundle, encoded

# Python 执行 zipapp 时，展开完整资源后才调用统一入口，保留原有相对路径约定。
ENTRY = '''"""展开完整发行资源并运行统一命令。"""
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

with tempfile.TemporaryDirectory(prefix="ai-dev-release-") as directory:
    with ZipFile(sys.argv[0]) as archive:
        archive.extractall(directory, [name for name in archive.namelist() if name != "__main__.py"])
    raise SystemExit(subprocess.call([
        sys.executable, str(Path(directory) / "scripts/ai-dev-standards"), *sys.argv[1:]
    ]))
'''.encode()


def build(toolkit: Path, ref: str, output: Path) -> tuple[Path, Path]:
    """只打包固定提交内受管资源，发布二进制和独立 SHA-256 校验文件。"""
    revision = subprocess.check_output(
        ["git", "-C", str(toolkit), "rev-parse", "--verify", "--end-of-options", ref + "^{commit}"],
        text=True,
    ).strip()
    data = subprocess.check_output(["git", "-C", str(toolkit), "archive", "--format=zip", revision])
    with tempfile.TemporaryDirectory(prefix="ai-dev-build-") as folder:
        source = Path(folder).resolve()
        with ZipFile(io.BytesIO(data)) as archive:
            archive.extractall(source)
        if not (source / "scripts/ai-dev-standards").is_file():
            raise BootstrapError("所选提交尚未包含 M5 统一入口")
        files, version = bundle(source)
    version.update(git_commit=revision, working_tree_dirty=False)
    stamp = {
        "owner": "ai-dev-standards",
        "schema_version": 1,
        "source": version,
        "files": {name: digest(body) for name, body in files.items() if name != STAMP},
    }
    files[STAMP] = encoded(stamp)
    files["__main__.py"] = ENTRY
    archive_bytes = io.BytesIO()
    with ZipFile(archive_bytes, mode="w") as archive:
        for name, body in sorted(files.items()):
            archive.writestr(ZipInfo(name), body, compress_type=ZIP_DEFLATED, compresslevel=9)
    payload = archive_bytes.getvalue()
    output.mkdir(parents=True, exist_ok=True)
    package = output / f"ai-dev-standards-{revision[:12]}.pyz"
    checksum = package.with_suffix(".sha256")
    if any(path.exists() or path.is_symlink() for path in (package, checksum)):
        raise BootstrapError("发行文件已存在，请使用新的输出目录")
    with package.open("xb") as handle:
        handle.write(payload)
    try:
        with checksum.open("x") as handle:
            handle.write(f"{digest(payload)}  {package.name}\n")
    except OSError:
        package.unlink()
        raise
    return package, checksum
