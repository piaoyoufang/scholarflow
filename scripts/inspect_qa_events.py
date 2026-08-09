# 导入命令行参数解析库，用来接收终端传入的参数
import argparse

# 导入问答事件全局单例，读取qa_events.sqlite里面的问答分析数据
from app.analytics.qa_events import qa_event_store


def main():
    """命令行分析脚本入口：在终端查看某一门课程的RAG问答统计数据"""
    # 创建参数解析器对象，用来定义、解析命令行参数
    parser = argparse.ArgumentParser()
    # 添加命令行参数 --course-id，设置为必填，运行脚本时必须传入该参数
    parser.add_argument("--course-id", required=True)
    # 解析终端传入的参数，结果存入args对象
    args = parser.parse_args()

    # 打印标题：高频问题统计
    print("=== 高频问题 ===")
    # 查询该课程的高频提问，循环打印：提问次数 + 问题文本
    for item in qa_event_store.top_questions(args.course_id):
        print(f"{item['count']} 次：{item['question']}")

    # 换行，打印标题：没有知识库引用的问答
    print("\n=== 无引用回答 ===")
    # 查询citation_count=0的记录，打印问题和创建时间
    for item in qa_event_store.no_citation_questions(args.course_id):
        print(f"- {item['question']} / {item['created_at']}")

    # 换行，打印标题：低质量 / 报错问答
    print("\n=== 低质量或失败回答 ===")
    # 查询低质量问答，打印问题、质量分数、错误信息
    for item in qa_event_store.low_quality_questions(args.course_id):
        print(f"- {item['question']} / score={item['quality_score']} / error={item['error']}")


# 判断脚本是否直接作为主程序运行（python xxx.py），如果是就执行main()函数
if __name__ == "__main__":
    main()