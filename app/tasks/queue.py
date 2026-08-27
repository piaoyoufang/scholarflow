"""arq 连接池单例：API 进程只负责把任务投进 Redis，不亲自执行
遵循仓库惯例：模块级单例（同 course_store / task_store 的模式），不引入 DI 容器"""
from arq import create_pool
from arq.connections import RedisSettings

from app.config import settings

_pool = None  # 模块级连接池，首次使用时惰性创建


async def get_queue():
    """获取 arq 连接池（懒加载单例）：enqueue_job 的入口"""
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool
