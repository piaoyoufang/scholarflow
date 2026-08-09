"""Read-only ScholarFlow diagnostics used as evidence by diagnosis_agent."""
from __future__ import annotations

import csv
from pathlib import Path

from app.config import PROJECT_ROOT, settings
from app.runtime_metrics import runtime_metrics
# 从 analytics 模块下 qa_events 文件导入全局单例对象 qa_event_store
from app.analytics.qa_events import qa_event_store


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _path_status(name: str, path: Path) -> str:
    if not path.exists():
        return f"{name}：不存在，路径={path}"
    if path.is_file():
        return f"{name}：存在，大小={path.stat().st_size}字节，路径={path}"
    size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return f"{name}：存在，目录文件总大小={size}字节，路径={path}"


def _report_summary(path: Path, report_name: str) -> str:
    if not path.exists():
        return f"{report_name}：尚未生成（{path.name}不存在）"
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    passed = sum(
        str(row.get("passed", "")).strip().lower() in {"true", "1", "yes"}
        for row in rows
    )
    return f"{report_name}：{passed}/{len(rows)}通过，文件={path.name}"

def course_quality_snapshot(course_id: str) -> dict:
    """
    获取课程RAG质量快照
    一次性返回该课程3类关键分析样本，用于前端展示课程RAG整体质量概览
    :param course_id: 目标课程ID
    :return: 字典，包含高频问题、无引用问答、低质量问答各最多5条
    """
    return {
        # 获取该课程提问最多的前5条问题
        "top_questions": qa_event_store.top_questions(course_id, limit=5),
        # 获取该课程回答没有引用来源的前5条记录
        "no_citation": qa_event_store.no_citation_questions(course_id, limit=5),
        # 获取该课程低质量/报错问答的前5条记录
        "low_quality": qa_event_store.low_quality_questions(course_id, limit=5),
    }


def collect_diagnostics() -> str:
    """Collect trusted local status without executing external commands."""
    path_lines = [
        _path_status("Chroma向量库", _resolve(settings.vector_db_dir)),
        _path_status("认证数据库", _resolve(settings.auth_db_path)),
        _path_status("记忆数据库", _resolve(settings.checkpoint_db_path)),
    ]
    report_lines = [
        _report_summary(PROJECT_ROOT / "reports" / "eval_report.csv", "通用评估"),
        _report_summary(
            PROJECT_ROOT / "reports" / "mcp_eval_report.csv",
            "MCP专项评估",
        ),
    ]
    metrics = runtime_metrics.snapshot()
    return "\n".join(
        [
            "ScholarFlow只读诊断证据",
            "数据文件状态：",
            *path_lines,
            "评估报告状态：",
            *report_lines,
            "运行指标（calls/successes/failures/retries/fallbacks）：",
            str(metrics) if metrics else "当前进程尚无运行指标",
        ]
    )
