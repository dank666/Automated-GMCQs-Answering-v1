# 项目更新日志 (CHANGELOG)

## 项目简介 (Project Introduction)
**Automated-GMCQs-Answering** (高中地理多项选择题自动化问答系统) 
本项目旨在通过自然语言处理(NLP)和三支形式概念分析(Three-way Concept Lattices)技术，实现地理单选与多项选择题的自动化解析和作答。系统通过提取题干中的地理特征、构建基于领域词典的实体关联矩阵、生成三支概念格，并最终提取出高置信度的地理推断规则，以此来自动映射并推断出正确选项。

---

## 2026-03-08 更新记录

### 1. 数据结构与题库规范化重构
* **题库 JSON 化**: 将原有的纯文本题库全面迁移为结构化的 JSON 格式，并按照地理学科类别拆分为多个题库文件（如 `single_Climatology.json`, `single_Geographical Processes and Principles.json` 等）。
* **词典重命名与规范化**: 编写脚本将原有的“词典*.csv”批量重命名为英文“dic*.csv”，解决跨平台编码及规范命名问题。

### 2. 核心流水线重构与性能优化
* **全新主控调度器 `batch_evaluate.py`**:
  * 移除了冗余且计算开销极大的旧版 `auto_run.py` 与 `main.py`（原版使用 `subprocess` 循环调用子进程）。
  * 实现了将所有题目放入同一个 Python 进程中循环处理的架构，使 `jieba` 分词和大型领域词典等耗时资产**仅需加载一次**。
  * 增加了针对前道题目生成的历史文本缓存清理机制，防止测试集之间的结果互相污染。
* **修复跨平台路径 Bug**: 移除了 `threeWcl.py` 中写死的 Windows 绝对路径（`C:\Users\...`），改为使用 `os.path.abspath(__file__)` 动态获取当前相对路径，使项目顺利跑通于 macOS 及 Linux。

### 3. 新增计算功能：自动化推断与准确率计算 (Inference Module)
* 在 `batch_evaluate.py` 尾部新增了选项推断模块。
* 支持根据 `extract_three_way_rules_enhanced.py` 吐出的“最高置信度和强度规则”，自动匹配 A/B/C/D 四个选项。
* 实现了**双模相似度匹配机制**（基于 jieba 分词的语义交集计算 + 基于字符级的重合度计算），从而容错选项中字面不完全一致的推断（如“夏季干热”自动关联到“干燥”选项）。
* 在所有题目分析结束时，自动输出 `batch_evaluation_summary.txt` 整体准确率报告。

### 4. 算法与逻辑 Bug 修复
* 修复了 `entity_attribute.py` 中 `get_top_similar_concepts()` 的一个致命逻辑 Bug：此前当题干特征与词典所有词打分均为 `0.0` 相似度时，代码依然会强行把排序榜首的不相关词汇牵扯进来纳入实体关联类中（导致如“喀斯特地貌”误入毫不相干的题目）。现在增加了 `> 0.0` 的绝对限制。

### 5. 垃圾文件清理
* 移除了项目重构后不再需要的废弃文件，包括：`auto_run.py`, `main.py`, `rename_dicts.py`, `test_questions.csv`。