"""arq worker 定义：独立进程运行，从 Redis 队列取 ingestion 任务执行
本地启动：python -m arq app.tasks.worker.WorkerSettings
容器启动：见 docker-compose.yml 的 worker 服务"""
import asyncio

from arq import Retry
from arq.connections import RedisSettings

from app.config import settings
from app.tasks.ingestion import run_ingestion_task
from app.tasks.store import task_store


async def ingestion_job(ctx, task_id: str, source_id: str, file_path: str, course_id: str | None):
    """队列任务包装：签名与 run_ingestion_task 对齐，参数随 enqueue_job 传入
    ctx 是 arq 注入的上下文（含 redis 连接、job_id、重试次数），本任务暂不需要"""
    # 幂等短路：重试/重复入队时，若任务已成功则直接返回，不重复入库
    # （向量写入按 (source_id, chunk_index) upsert，天然幂等，这里再加一道状态闸）
    task = task_store.get_task(task_id)
    if task and task.get("status") == "success":
        return

    # run_ingestion_task 是同步阻塞函数（解析 PDF、embedding），
    # 用 asyncio.to_thread 丢到线程池执行，避免卡住 worker 的事件循环
    await asyncio.to_thread(run_ingestion_task, task_id, source_id, file_path, course_id)

    # run_ingestion_task 内部吞掉所有异常（标记任务 failed 后正常返回），
    # 所以重读任务状态把失败转成异常交还给 arq。
    # 注意 arq 语义：普通异常直接判死（不重试），只有 Retry 异常会按 max_tries 重试；
    # defer=5 秒退避，避免瞬时故障（网络抖动、DashScope 限流）被立即重打
    task = task_store.get_task(task_id)
    if task and task.get("status") == "failed":
        raise Retry(defer=5)


class WorkerSettings:
    """arq 的 worker 配置类：命令行 python -m arq 按模块路径加载它"""
    functions = [ingestion_job]
    max_tries = 3                                    # 失败自动重试最多 3 次——BackgroundTasks 给不了的能力
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
