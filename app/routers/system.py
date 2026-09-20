"""系统域路由：首页、健康检查、存活/就绪探针、运行时指标——从 api.py 原样搬入"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import current_session
from app.health import readiness_report
from app.runtime_metrics import runtime_metrics

router = APIRouter()

# 首页根路径接口，访问展示服务运行状态与文档地址
@router.get("/", tags=["系统"], summary="服务首页")
def root():
    return {
        "message": "ScholarFlow API is running",
        "docs": "http://127.0.0.1:8000/docs",
    }

# 健康检测接口，运维监控/负载均衡用于检测服务存活
@router.get("/health", tags=["系统"], summary="健康检查")
def health():
    return {"status": "ok"}


# FastAPI接口装饰器，定义GET存活探针路由，用于容器/集群检测服务进程是否存活
@router.get("/health/live", tags=["系统"], summary="存活检查")
def liveness():
    # 简单返回存活标识，只要进程正常运行就能响应，不校验业务依赖
    return {"status": "alive"}


# FastAPI接口装饰器，定义GET就绪探针路由，校验所有数据库、向量目录依赖是否可用
@router.get("/health/ready", tags=["系统"], summary="就绪检查")
def readiness():
    # 执行全量存储资源健康检查，获取数据库、向量目录状态报告
    report = readiness_report()
    # 判断任意存储资源异常，服务未就绪
    if not report["ready"]:
        # 抛出503服务不可用异常，携带完整故障明细给负载均衡/容器编排
        raise HTTPException(
            # HTTP状态码503：服务暂时无法处理请求
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            # detail携带完整检查明细，方便运维定位故障库/目录
            detail=report,
        )
    # 全部存储资源正常，返回健康明细报告
    return report


# FastAPI接口装饰器，定义GET请求路由，用于查询全系统运行时性能监控指标
@router.get("/metrics/runtime", tags=["运行监控"], summary="查看运行时指标")
def get_runtime_metrics(
    # 依赖注入校验当前登录会话，返回(user_id, token)二元组，未登录会直接拦截请求
    session: tuple[str, str] = Depends(current_session),
):
    # 解包会话元组，提取用户ID（token此处无业务使用，下划线丢弃）
    user_id, _token = session
    # 组装并返回监控指标响应体
    return {
        # 当前请求操作者的用户ID，用于接口访问日志溯源
        "user_id": user_id,
        # 调用全局指标单例生成完整统计快照，包含各组件调用次数、耗时、失败、降级数据
        "components": runtime_metrics.snapshot(),
    }
