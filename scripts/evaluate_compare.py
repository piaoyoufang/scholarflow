"""回归对比：两份 evaluate_run 报告的指标 diff
固定工作流：改检索参数 → 跑 evaluate_run → compare 对比 → 决定保留或回滚
运行：python -m scripts.evaluate_compare reports/before.json reports/after.json
"""
import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("用法：python -m scripts.evaluate_compare 旧报告.json 新报告.json")
    before = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    after = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

    # 先核对参数快照：把指标差异和「其实是换了模型」区分开，快照不同则对比结论不可归因
    for key in ("chat_model", "embedding_model", "rerank_model"):
        if before["snapshot"].get(key) != after["snapshot"].get(key):
            print(f"⚠ 快照不一致：{key}  {before['snapshot'].get(key)} → {after['snapshot'].get(key)}")

    # 指标总表：改动前后 + 差值；0.005 以内的波动视为噪声
    print(f"\n{'指标':<24}{'改动前':>8}{'改动后':>8}   差值")
    for key, new_val in after["metrics"].items():
        old_val = before["metrics"].get(key, 0)
        delta = new_val - old_val
        arrow = "↑" if delta > 0.005 else ("↓" if delta < -0.005 else "→")
        print(f"{key:<24}{old_val:>8}{new_val:>8}   {arrow} {delta:+.3f}")

    # 逐题下钻：列出「变好/变差」的题，调优时最该关注的是变差的题
    before_cases = {c["question"]: c for c in before["cases"]}
    changed = 0
    for c in after["cases"]:
        b = before_cases.get(c["question"])
        if not b:
            continue
        diffs = []
        for key in ("source_hit", "refusal_correct", "pass_result"):
            if b.get(key) != c.get(key):
                diffs.append(f"{key} {b.get(key)}→{c.get(key)}")
        if diffs:
            changed += 1
            print(f"  变化题：{c['question']}  " + "，".join(diffs))
    if not changed:
        print("\n逐题对比：无变化题")


if __name__ == "__main__":
    main()
