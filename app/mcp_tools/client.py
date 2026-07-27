"""这份代码是你之前 MCP 客户端的重构增强版本：
支持调用两个 MCP 工具：search_local_knowledge（本地知识库）、search_evaluation_report（评估报表查询）
增加 ALLOWED_TOOLS 白名单安全校验，禁止随意调用未知工具
抽取通用call_tool_via_mcp作为底层公共函数，消除重复代码
向下兼容：保留旧名称search_via_mcp / search_via_mcp_sync，之前写好的所有脚本不需要修改就能继续运行
同时提供异步接口 + 同步封装接口，适配 LangGraph 同步 / 异步节点
配套 MCP Server 上现在注册了两个 tool，客户端统一通过这一套代码调用。"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app.config import settings
from app.resilience import run_async_with_retry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
# 工具白名单（安全机制）
ALLOWED_TOOLS = {
    "search_local_knowledge",
    "search_evaluation_report",
}

# 构造启动 MCP Server 的参数对象
def server_parameters() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_tools.server"],
        cwd=str(PROJECT_ROOT),
    )

# list_mcp_tools 查询服务端可用工具
async def list_mcp_tools() -> list[str]:
    async with stdio_client(server_parameters()) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.list_tools()
            return [tool.name for tool in response.tools]

# 单次调用MCP工具的异步私有函数，发起一次MCP服务调用并解析返回JSON结果
# tool_name：需要调用的MCP工具标识名称
# query：传给工具的检索/查询关键词
# top_k：工具返回结果的最大条数限制
# 返回值：工具输出的结构化字典列表
async def _call_tool_once(
    tool_name: str,
    query: str,
    top_k: int,
) -> list[dict[str, Any]]:
    # 建立MCP标准IO客户端连接，读取、写入数据流，自动释放连接资源
    async with stdio_client(server_parameters()) as (read_stream, write_stream):
        # 使用MCP客户端会话，绑定读写流，会话结束自动关闭
        async with ClientSession(read_stream, write_stream) as session:
            # 初始化MCP会话握手，和MCP服务建立通信通道
            await session.initialize()
            # 异步发起工具调用，传入工具名与入参
            response = await session.call_tool(
                # 目标MCP工具名称
                tool_name,
                # 工具所需入参打包
                arguments={"query": query, "top_k": top_k},
            )

            # 判断MCP返回状态为错误时，主动抛出运行时异常供外层捕获重试
            if response.isError:
                raise RuntimeError(f"MCP 工具返回错误：{tool_name}")

            # 遍历返回内容块，只提取存在text属性的文本片段
            text_parts = [
                block.text
                for block in response.content
                if hasattr(block, "text")
            ]
            # 没有任何文本返回，直接返回空列表兜底
            if not text_parts:
                return []
            # 拼接全部文本，解析JSON字符串，返回结构化字典数组
            return json.loads("".join(text_parts))


# 对外统一调用MCP工具的异步入口函数，包含工具白名单校验、自动重试、超时管控、性能埋点
# tool_name：待调用的MCP工具名称
# query：工具查询入参文本
# top_k：工具返回数据条数，默认3条
# 返回值：MCP工具解析后的结构化字典列表
async def call_tool_via_mcp(
    tool_name: str,
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    # 安全校验：校验工具是否在允许调用的白名单内
    if tool_name not in ALLOWED_TOOLS:
        # 不在白名单直接抛出参数非法异常，阻断高危/未授权工具调用
        raise ValueError(f"不允许调用的 MCP 工具：{tool_name}")

    # 调用异步重试执行器，封装单次MCP调用逻辑
    return await run_async_with_retry(
        # lambda封装单次MCP工具底层调用函数
        lambda: _call_tool_once(tool_name, query, top_k),
        # 监控组件标识，按工具名拆分指标（mcp.xxx），单独统计各工具耗时、失败率
        component=f"mcp.{tool_name}",
        # 单次MCP调用超时时间，读取全局配置MCP_TIMEOUT_SECONDS
        timeout_seconds=settings.mcp_timeout_seconds,
        # MCP接口最大重试次数，读取全局配置MCP_MAX_ATTEMPTS
        max_attempts=settings.mcp_max_attempts,
    )

# 同步包装函数 call_tool_via_mcp_sync
def call_tool_via_mcp_sync(
    tool_name: str,
    query: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    return asyncio.run(
        call_tool_via_mcp(tool_name=tool_name, query=query, top_k=top_k)
    )


# 保留旧函数，避免第 10、11、12 步已有脚本立刻失效。
async def search_via_mcp(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    return await call_tool_via_mcp(
        tool_name="search_local_knowledge",
        query=query,
        top_k=top_k,
    )


def search_via_mcp_sync(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    return call_tool_via_mcp_sync(
        tool_name="search_local_knowledge",
        query=query,
        top_k=top_k,
    )