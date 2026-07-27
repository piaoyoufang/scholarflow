# 导入json工具，用于解析jsonl单行日志
import json
# 导入警告过滤模块，屏蔽无关弃用告警
import warnings
# UUID工具，生成唯一测试请求ID
from uuid import uuid4

# Starlette框架弃用警告类型，用于精准过滤测试无关提示
from starlette.exceptions import StarletteDeprecationWarning

# 全局过滤Starlette版本兼容告警，不干扰日志测试结果
warnings.filterwarnings("ignore", category=StarletteDeprecationWarning)

# FastAPI测试客户端，模拟HTTP请求访问项目接口
from fastapi.testclient import TestClient

# 导入项目api入口模块，加载FastAPI应用实例
from app import api as api_module
# 导入日志工具函数，获取日志文件绝对路径
from app.observability import log_file_path


def main() -> None:
    """可观测性日志链路自动化测试脚本
    校验3项核心能力：请求ID透传响应头、jsonl日志文件正常生成、日志完整携带请求元数据
    """
    # 生成本次测试唯一追踪request_id，区分其他请求日志
    request_id = f"observability-test-{uuid4().hex[:8]}"

    # 实例化测试客户端，模拟HTTP请求链路
    with TestClient(api_module.app) as client:
        # 调用健康检查接口，手动传入自定义X-Request-ID请求头
        response = client.get(
            "/health",
            headers={"X-Request-ID": request_id},
        )

    # 断言健康接口必须返回200正常状态码，失败打印接口原始返回文本
    assert response.status_code == 200, response.text
    # 断言响应头原样回传前端传入的request_id，校验链路追踪ID透传功能
    assert response.headers.get("X-Request-ID") == request_id, (
        "响应头没有返回原请求的X-Request-ID"
    )

    # 获取项目日志文件完整绝对路径
    path = log_file_path()
    # 断言日志文件已成功创建，文件不存在直接测试失败
    assert path.exists(), f"日志文件不存在：{path}"

    # 初始化匹配日志记录容器，未找到则保持None
    matched_record = None
    # 读取日志文件全部文本，按行分割，倒序遍历（最新日志在文件末尾，优先匹配）
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        try:
            # 单行jsonl日志反序列化为字典
            record = json.loads(line)
        # 捕获非标准JSON脏日志行，跳过不中断循环
        except json.JSONDecodeError:
            continue

        # 匹配条件：日志携带本次测试request_id、事件为正常请求完成
        if (
            record.get("request_id") == request_id
            and record.get("event") == "request.completed"
        ):
            # 命中目标日志行，赋值并跳出循环
            matched_record = record
            break

    # 断言：日志文件中必须找到本次测试对应的请求记录
    assert matched_record is not None, "日志中没有找到本次测试请求"
    # 提取日志内业务详情字段
    details = matched_record["details"]
    # 校验请求方法为GET
    assert details["method"] == "GET"
    # 校验请求接口路径为健康检查 /health
    assert details["path"] == "/health"
    # 校验日志记录接口返回200状态码
    assert details["status_code"] == 200
    # 校验接口耗时字段为数字类型（整数/浮点数均可）
    assert isinstance(details["duration_ms"], (int, float))

    # 全部校验通过，依次打印测试结果
    print("X-Request-ID响应头：通过")
    print("JSONL日志文件生成：通过")
    print("请求方法、路径、状态码、耗时字段：通过")
    print(f"日志路径：{path}")


# 脚本直接运行时，执行全套日志链路自动测试
if __name__ == "__main__":
    main()