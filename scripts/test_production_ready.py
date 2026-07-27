# 导入路径处理工具类，用于校验项目根目录下生产部署必需文件
from pathlib import Path
# FastAPI内置测试客户端，模拟HTTP请求调用接口
from fastapi.testclient import TestClient

# 导入后端FastAPI主应用实例
from app.api import app
# 导入项目根目录全局常量
from app.config import PROJECT_ROOT
# 导入存储资源就绪健康检测函数
from app.health import readiness_report

# 实例化测试客户端，绑定后端应用
client = TestClient(app)

# 通用断言工具，条件不满足则抛出断言错误，附带提示信息
def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)

# 服务整体集成健康校验入口脚本
def main() -> None:
    # 调用存活探针接口 /health/live
    live = client.get("/health/live")
    # 校验接口返回状态码200，代表进程正常响应
    check(live.status_code == 200, "存活检查不是200")
    # 校验返回JSON标识为alive
    check(live.json()["status"] == "alive", "存活响应内容错误")
    print("存活检查：通过")

    # 调用就绪探针接口 /health/ready，校验数据库、向量目录全部可用
    ready = client.get("/health/ready")
    # 校验就绪接口正常返回200，失败时打印接口原始报错文本
    check(ready.status_code == 200, f"就绪检查失败：{ready.text}")
    # 校验全局就绪标记为True，所有存储资源正常
    check(ready.json()["ready"] is True, "就绪状态不是true")
    print("SQLite与向量目录就绪检查：通过")

    # 定义生产部署必须存在的Docker相关配置文件清单
    required_files = [
        PROJECT_ROOT / "Dockerfile",
        PROJECT_ROOT / "docker-compose.yml",
        PROJECT_ROOT / ".dockerignore",
        PROJECT_ROOT / ".env.production.example",
    ]
    # 过滤出不存在的文件，转为字符串列表
    missing = [str(path) for path in required_files if not path.exists()]
    # 存在缺失文件直接断言失败，提示缺失文件路径
    check(not missing, f"缺少生产文件：{missing}")
    print("Docker生产文件：通过")

    # 直接调用底层健康检测函数，校验返回数据结构完整性
    report = readiness_report()
    # 校验报告包含明细checks字段，保证接口返回结构规范
    check("checks" in report, "就绪报告缺少checks")
    print("就绪报告结构：通过")

# 脚本直接运行时执行全套健康集成测试
if __name__ == "__main__":
    main()
