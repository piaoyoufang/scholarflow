# 命令行入口脚本。它的作用是让用户可以在终端（Terminal）里通过一行命令，把指定的文件“喂”给系统进行处理。
import sys  # 我们需要用它来接收你在命令行输入的参数（比如你输入的文件路径）。没有它，程序就不知道你要处理哪个文件。
from app.ingestion.loader import ingest # 这里引用了你之前看过的 loader.py 里的 ingest 函数。这个函数包含了读取 PDF、切分文本、存入向量库的所有逻辑

"""作用： 检查用户输入的命令格式是否正确。
详解：
sys.argv 是一个列表，存储了命令行输入的所有内容。
len(sys.argv) 计算列表长度。
当你输入 python -m scripts.ingest data/raw/course.pdf 时：
sys.argv[0] 是脚本名 (scripts.ingest)
sys.argv[1] 是参数 (data/raw/course.pdf)
所以合法的输入长度必须是 2。如果用户忘了输文件名，或者多输了东西，这里就会拦截。"""
if len(sys.argv) != 2:
    raise SystemExit("用法: python -m scripts.ingest data/raw/course.pdf") #  如果上面的检查没通过（比如用户直接运行了脚本没带参数），程序会立即停止，并在屏幕上打印出正确的用法提示，告诉用户该怎么写命令。
print(f"已写入 {ingest(sys.argv[1])} 个片段")
#