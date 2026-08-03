# 启用Python前向类型注解，允许先使用后定义的类型标注
from __future__ import annotations

# 正则表达式库，用于校验语义化版本号格式
import re
# 子进程调用工具，执行python模块、编译字节码等系统命令
import subprocess
# 获取当前运行的Python解释器路径
import sys
# 跨平台路径处理工具
from pathlib import Path

# 计算项目根目录：当前脚本文件的上级上一级目录
ROOT = Path(__file__).resolve().parents[1]

# 语义化版本号正则匹配规则
# 匹配标准格式：主版本.次版本.修订号，可选带预发布后缀（如 1.2.3-beta1）
VERSION_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?$"
)

# 发布上线前必须存在的核心文件清单
REQUIRED_FILES = [
    "VERSION",                  # 版本号文本文件
    "CHANGELOG.md",             # 更新日志文档
    "RELEASE_CHECKLIST.md",     # 发布核对清单
    "requirements.lock.txt",    # 锁定版本依赖清单（保证环境一致性）
    "Dockerfile",               # 容器构建文件
    "docker-compose.yml",       # 容器编排配置
    ".dockerignore",            # Docker打包忽略文件
    ".env.production.example",  # 生产环境变量模板
]

# 离线自动化测试模块列表（无需调用大模型/外部服务，纯本地单元/集成校验）
OFFLINE_MODULES = [
    "scripts.test_account_auth",    # 账号权限认证测试
    "scripts.test_token_lifecycle", # Token生命周期校验
    "scripts.test_thread_permissions",# 多线程权限控制测试
    "scripts.test_thread_history_api",# 线程列表与历史恢复接口测试
    "scripts.test_summary_memory",   # 长期摘要与checkpoint持久化测试
    "scripts.test_observability",   # 监控指标埋点校验
    "scripts.test_rate_limit",      # 接口限流逻辑测试
    "scripts.test_multi_agent",     # 多Agent分流流程测试
    "scripts.test_diagnosis_agent", # 只读诊断Agent测试
    "scripts.test_resilience",      # 重试、降级容灾逻辑测试
    "scripts.test_production_ready",# 生产环境就绪性全量校验脚本
]


# 统一封装Python模块执行函数
# arguments：需要传给python -m 的模块/参数列表
def run(arguments: list[str]) -> None:
    # 拼接完整执行命令：当前解释器 + 传入参数
    command = [sys.executable, *arguments]
    # 打印分隔线与待执行命令，flush=True 强制立刻输出日志
    print("=" * 80)
    print("运行：", " ".join(command), flush=True)
    # 子进程执行命令，工作目录锁定项目根目录
    # check=True：命令执行异常（非0退出码）直接抛出异常终止整个发布校验
    subprocess.run(command, cwd=ROOT, check=True)


# 发布前置文件、版本、日志完整性校验函数
# 返回读取到的合法版本号字符串
def check_release_files() -> str:
    # 过滤出清单中不存在的发布必需文件
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).exists()]
    # 存在缺失文件，直接退出脚本并提示
    if missing:
        raise SystemExit(f"缺少发布文件：{missing}")

    # 读取VERSION文件内的版本号，去除首尾空白换行
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    # 使用正则完整匹配校验是否符合语义化版本规范
    if not VERSION_PATTERN.fullmatch(version):
        raise SystemExit(f"VERSION不是合法语义化版本：{version!r}")

    # 读取更新日志全文
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # 校验日志内存在当前版本对应的更新章节（标准格式## [x.y.z]）
    if f"## [{version}]" not in changelog:
        raise SystemExit(f"CHANGELOG.md缺少版本章节：{version}")

    # 文件与版本校验全部通过，打印日志并返回版本号
    print(f"发布文件与版本号检查：通过（{version}）")
    return version


# 发布门禁脚本主流程
def main() -> None:
    # 第一步：校验所有发布文件、版本号、更新日志合法性
    version = check_release_files()
    # 编译全项目Python代码，静默执行，提前捕获语法错误
    run(["-m", "compileall", "-q", "app", "scripts", "ui.py"])

    # 循环执行所有离线自动化测试模块
    for module in OFFLINE_MODULES:
        run(["-m", module])

    # 所有离线校验全部执行完成，输出完成提示
    print("=" * 80)
    print(f"ScholarFlow v{version} 离线发布门禁：全部通过")
    # 关键提示：本套测试不调用真实Qwen大模型，仅离线校验；上线前仍需手动完成真实大模型评估、容器构建验收
    print("本脚本没有调用真实Qwen；发布前仍需完成真实评估和容器验收。")


# 脚本直接运行时，执行整套发布门禁校验流程
if __name__ == "__main__":
    main()
