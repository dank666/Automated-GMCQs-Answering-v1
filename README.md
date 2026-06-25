# 地理选择题自动解答系统使用说明

本项目是一个面向高中地理单选题与多选题的自动解答系统。系统以 `batch_evaluate.py` 为统一入口，结合领域词典、关键词抽取、实体属性关联、形式背景构建、三支概念格计算、规则抽取和动态概念检索，实现对结构化地理题库的批量推理与准确率评估。

本文档是当前仓库唯一保留的 Markdown 说明文件，包含系统介绍、运行方法、动态概念检索模块、输出文件说明、实验报告解读和论文写作注意事项。

## 1. 系统概览

系统原始版本是一个基于静态地理词典和三支概念分析的符号推理系统。基本流程为：

```text
题库 JSON
  -> 关键词提取
  -> 领域词典匹配
  -> 实体属性抽取
  -> 形式背景构建
  -> 三支概念格计算
  -> 条件概念与决策概念合并
  -> 规则提取
  -> 选项评分与答案推断
  -> 准确率评估
```

加入动态概念检索（Dynamic Concept Retrieval, DCR）后，系统扩展为：

```text
题库 JSON
  -> 原词典基线测试
  -> 错题或全题陌生术语检测
  -> LLM 动态检索概念关系
  -> 自动扩展 CSV 词典
  -> 清理词典缓存
  -> 二次完整测试
  -> 默认仅统计系统自身预测
  -> 输出前后准确率差异
```

## 2. 核心文件

| 文件 | 作用 |
| --- | --- |
| `batch_evaluate.py` | 主入口，支持普通批测和 DCR 两阶段批测 |
| `geo_keyword_extractor.py` | 关键词抽取、同义词规范化、领域词典加载 |
| `geo_keyword_extractor_dcr_integration.py` | 关键词提取器与 DCR 的集成层 |
| `dynamic_concept_retrieval.py` | DCR 核心，负责 LLM 调用、概念解析、词典更新和缓存 |
| `entity_attribute.py` | 构建实体、属性和选项相关关系 |
| `formal_context_builder.py` | 构建形式背景矩阵和中间文件 |
| `threeWcl.py` | 三支概念格计算 |
| `process_result_decision.py` | 决策概念结果偏移处理 |
| `merge_concepts.py` | 合并条件概念和决策概念 |
| `extract_three_way_rules_enhanced.py` | 规则提取和规则强度计算 |
| `enrich_single_dictionaries.py` | 基于单选题库补强单选词典 |
| `enrich_multiple_dictionaries.py` | 基于多选题库补强多选词典 |
| `paint.py` | 绘制结果对比图 |

## 3. 目录结构

```text
.
├── batch_evaluate.py
├── dynamic_concept_retrieval.py
├── geo_keyword_extractor.py
├── geo_keyword_extractor_dcr_integration.py
├── entity_attribute.py
├── formal_context_builder.py
├── threeWcl.py
├── process_result_decision.py
├── merge_concepts.py
├── extract_three_way_rules_enhanced.py
├── dict_single/
├── dict_multiple/
├── dict_backup/
├── single_questions/
├── multiple_questions/
├── test_contexts/
├── test_results/
├── figures/
├── interface_photo/
└── README.md
```

## 4. 运行环境

建议使用 Python 3.10。

基础依赖：

```bash
pip install pandas numpy jieba matplotlib requests openai
```

如果使用 Anthropic：

```bash
pip install anthropic
```

如果使用本地模型，例如 Ollama，需要先启动本地服务。

## 5. 题库和词典格式

### 5.1 题库 JSON

题库文件顶层字段为 `geography_questions`。

单题格式示例：

```json
{
  "id": 1,
  "type": "single",
  "geography_category": "Soil and Vegetation",
  "difficulty": "medium",
  "question": "题干文本",
  "options": {
    "A": "选项A",
    "B": "选项B",
    "C": "选项C"
  },
  "correct_answer": ["A"],
  "explanation": ""
}
```

多选题将 `type` 设为 `"multiple"`，并在 `correct_answer` 中填写多个选项，例如：

```json
"correct_answer": ["A", "B"]
```

### 5.2 领域词典 CSV

词典必须包含以下列：

```text
关键字,分类,上级,下级
```

示例：

```text
盐碱化,土壤与植被,土壤退化、干旱区生态环境问题,地下水位上升、蒸发旺盛、地表积盐
```

单选词典位于：

```text
dict_single/
```

多选词典位于：

```text
dict_multiple/
```

干净备份词典位于：

```text
dict_backup/
```

## 6. 普通批量评测

不启用 DCR 时，系统只使用静态词典和符号推理流程。

### 6.1 单选题

```bash
python batch_evaluate.py single_questions/Soil_and_Vegetation.json \
  -d dict_single/SV.csv
```

### 6.2 多选题

```bash
python batch_evaluate.py multiple_questions/Soil_and_Vegetation.json \
  -d dict_multiple/SV.csv
```

建议始终显式使用 `-d` 指定词典文件。

## 7. 动态概念检索模块 DCR

### 7.1 DCR 的作用

DCR 用于解决静态词典覆盖不足的问题。当系统发现某些题目中的关键词或地理术语不在当前词典中时，DCR 会调用大语言模型生成结构化概念信息，并自动写回 CSV 词典。

DCR 生成的信息仍然使用系统原有词典格式：

```text
关键字,分类,上级,下级
```

因此它不是简单地让大模型直接答题，而是把大模型知识转化为符号系统可使用的词典条目。

### 7.2 DCR 支持的模型

当前支持：

```text
deepseek
openai
anthropic
local
```

DeepSeek 推荐配置：

```bash
export DEEPSEEK_API_KEY="你的DeepSeek Key"
```

OpenAI：

```bash
export OPENAI_API_KEY="你的OpenAI Key"
```

Anthropic：

```bash
export ANTHROPIC_API_KEY="你的Anthropic Key"
```

也可以临时传入：

```bash
--api-key "你的Key"
```

### 7.3 启用 DCR

```bash
python batch_evaluate.py single_questions/Soil_and_Vegetation.json \
  -d dict_single/SV.csv \
  --enable-dcr \
  --llm-provider deepseek
```

多选题：

```bash
python batch_evaluate.py multiple_questions/Soil_and_Vegetation.json \
  -d dict_multiple/SV.csv \
  --enable-dcr \
  --llm-provider deepseek
```

### 7.4 DCR 扩展范围

默认：

```bash
--dcr-target wrong
```

含义是：先做一次基线测试，然后只针对基线答错题进行 DCR 检索和词典扩展。二次评测默认不使用大模型直接改答案，准确率只统计扩展词典后系统自身的预测结果。

如果希望对全部题目检测陌生术语：

```bash
--dcr-target all
```

示例：

```bash
python batch_evaluate.py multiple_questions/Soil_and_Vegetation.json \
  -d dict_multiple/SV.csv \
  --enable-dcr \
  --llm-provider deepseek \
  --dcr-target all
```

## 8. DCR 的工作原理

### 8.1 陌生术语检测

系统先用当前词典进行关键词提取。如果候选关键词不在词典中，就可能成为 DCR 候选词。

为避免词典污染，系统会过滤低价值词，例如：

```text
一个、主要、同时、影响、形成、决定、根据、当地、变化规律
```

也会过滤纯数字、过短词和明显碎片化词。

### 8.2 上下文感知检索

DCR 不只询问模型“某个词是什么意思”，还会提供：

- 待补充术语
- 当前题干
- 当前选项
- 当前词典示例

这样模型生成的上级、下级概念更贴近题目中的判断关系。

### 8.3 结构化概念生成

模型被要求只返回 JSON，例如：

```json
{
  "分类": "土壤与植被",
  "上级": "土壤退化、干旱区生态环境问题、灌溉农业",
  "下级": "地下水位上升、蒸发旺盛、地表积盐、次生盐渍化",
  "confidence": 0.85
}
```

当置信度过低时，该词条不会写入词典。

### 8.4 自动更新词典

检索成功后，新词条会被追加到当前 `-d` 指定的 CSV 词典中。

因此正式实验前建议复制一份测试词典：

```bash
cp dict_backup/dict_single/SV.csv dict_single/SV_dcr_test.csv
```

然后使用测试词典运行：

```bash
python batch_evaluate.py single_questions/Soil_and_Vegetation.json \
  -d dict_single/SV_dcr_test.csv \
  --enable-dcr \
  --llm-provider deepseek
```

### 8.5 缓存机制

DCR 缓存位于：

```text
.dcr_cache/concept_cache.json
```

当前缓存键使用：

```text
术语 + 上下文哈希
```

这样可以避免早期无上下文检索结果污染后续上下文感知检索。

### 8.6 DCR 辅助判题

对于单选题，原系统有时会出现多个选项分数接近、错误选项因词汇重合而得分偏高的情况。

DCR 辅助判题是旧版实验中的可选上限分析，不再默认启用。它会在 DCR 流程中对基线答错的单选题进行二次判断。输入包括：

- 题干
- 选项
- DCR 检索或当前词典中的相关概念信息

模型只输出一个选项标签，例如：

```json
{"answer": "A", "confidence": 0.85}
```

第二轮完整测试时，该结果会覆盖原系统对该题的预测。

只有显式加入以下参数时才会启用该覆盖：

```bash
--enable-dcr-answer-override
```

启用后得到的是“系统 + 大模型判题覆盖”的后验修复结果，不能作为纯符号系统自身准确率。

## 9. DCR 两阶段流程

启用 DCR 后，系统执行：

1. **阶段 1：基线测试**
   - 使用原始词典完整评测题库。

2. **阶段 2：错题或全题术语检测**
   - 默认只检测基线答错题。

3. **阶段 3：动态扩词**
   - 调用 LLM 检索陌生术语。
   - 写入 CSV 词典。

4. **阶段 3.5：答案覆盖控制**
   - 默认跳过 DCR 辅助判题。
   - 只有传入 `--enable-dcr-answer-override` 时，才会对 DCR 覆盖的单选错题进行大模型辅助判题。

5. **阶段 4：二次完整测试**
   - 使用扩展后的词典重新测试完整题库。
   - 默认输出“扩展词典后系统自身”的准确率变化。

## 10. 输出文件

普通评测输出：

```text
test_results/batch_evaluation_summary.txt
```

DCR 评测还会输出：

```text
test_results/dcr_evaluation_summary.txt
test_results/dcr_evaluation_report.json
test_results/dcr_missing_concepts.json
test_results/dcr_affected_questions.json
```

其中 `dcr_evaluation_summary.txt` 包含：

- 基线整体准确率
- DCR 后整体准确率
- 整体准确率变化
- DCR 覆盖题目前后准确率
- 成功扩展词条数
- 检索失败词条数
- DCR 辅助判题覆盖数
- DCR 辅助判题是否启用

`dcr_evaluation_report.json` 包含更详细的信息：

- 每个 DCR 覆盖题目的前后预测
- 正确答案
- 改善、下降、不变数量
- 新增词条详情
- 辅助判题覆盖结果

## 11. 为什么要区分 DCR 扩词和 DCR 辅助判题

当前默认流程中，即使使用：

```bash
--dcr-target wrong
```

系统也只是利用基线结果定位需要扩展词典的错题，二次评测不会让大模型直接覆盖系统预测。因此，默认 DCR 后准确率表示“扩展词典后系统自身的准确率”。

如果显式加入：

```bash
--enable-dcr-answer-override
```

系统会用大模型对部分单选错题直接输出选项，并在二次评测中覆盖原系统预测。这类结果可能显著升高，甚至接近满分，但它表示“系统 + 大模型判题覆盖”的后验修复上限，不是系统自身能力。

因此论文中必须区分：

| 实验类型 | 是否使用标准答案定位错题 | 含义 |
| --- | --- | --- |
| 静态词典基线 | 否 | 原符号系统性能 |
| DCR 全量扩词 | 否 | 更接近公平增强 |
| DCR 错题扩词 | 是 | 后验扩词分析，仍统计系统自身预测 |
| DCR 辅助判题覆盖 | 是 | LLM 辅助错题修复上限 |

建议论文中将 99% 或 100% 表述为：

```text
DCR 辅助判题覆盖后的准确率
```

而不是直接表述为：

```text
完全公平测试准确率
```

## 12. 论文中可以采用的表述

可以写为：

> 本文在原有三支概念推理框架基础上，引入动态概念检索模块。该模块用于缓解静态领域词典覆盖不足的问题。当系统在题干和选项中检测到词典未覆盖的地理术语时，DCR 调用大语言模型生成结构化概念信息，包括概念分类、上级概念和下级概念，并将其转化为与原词典格式一致的条目。扩展后的词典进一步参与关键词提取、实体属性构建、形式背景生成、三支概念计算和规则提取，从而实现对原符号推理链的知识增强。

还可以写为：

> 为评估 DCR 对系统自身推理能力的增强效果，本文设计了两阶段扩词实验。第一阶段使用静态词典系统完成基线测试；第二阶段针对目标样本进行动态概念检索，并将检索到的结构化知识写入领域词典。随后系统在不使用大模型直接判题的条件下重新完成完整题库评测，用以前后准确率变化衡量词典扩展对原符号推理链的贡献。

必须说明：

> 默认 `--dcr-target wrong` 使用基线错误样本进行后验扩词，因此该结果主要用于分析错题相关词典补强效果；若要评估完全无反馈部署场景，应使用 `--dcr-target all` 并报告不启用 `--enable-dcr-answer-override` 的结果。

## 13. 推荐实验表格

| 系统版本 | DCR | 辅助判题 | 错题定位 | 准确率 | 说明 |
| --- | --- | --- | --- | --- | --- |
| 静态词典基线 | 否 | 否 | 否 | xx% | 原系统 |
| DCR 全量扩词 | 是 | 否 | 否 | xx% | 更公平的系统增强 |
| DCR 错题扩词 | 是 | 否 | 是 | xx% | 后验扩词分析，仍统计系统自身 |
| DCR 判题覆盖 | 是 | 是 | 是 | xx% | 大模型辅助修复上限 |

也建议记录：

- 新增词条数量
- 检索失败数量
- 辅助判题覆盖数
- 改善题数
- 下降题数
- 不变题数

## 14. 注意事项

1. **词典会被自动修改**
   - DCR 会把新词条写入 `-d` 指定的 CSV。
   - 正式实验前建议复制备份词典。

2. **不要泄露 API Key**
   - 不要把真实 API Key 写入 README 或提交到仓库。

3. **区分公平评估和后验修复**
   - `--dcr-target wrong` 会使用标准答案定位错题。
   - 论文中必须说明这是后验增强实验。

4. **多次运行同一个词典时，陌生词可能变少**
   - 因为上一轮 DCR 已经把词写入了 CSV。
   - 当前系统在没有新陌生词时，会直接用当前词典进行二次系统评测。

5. **三支概念数量异常大时要检查词典污染**
   - 如果词典混入大量泛词或长句，概念数量会暴涨。
   - 可以从 `dict_backup/` 复制干净词典重新实验。

## 15. 敏感性分析实验

敏感性分析用于回应审稿人关于规则筛选阈值鲁棒性的质疑。该实验只改变三支概念规则提取阶段的阈值参数，不启用 DCR，也不调用大模型辅助判题。

### 15.1 可调参数

实验脚本通过环境变量控制四个参数：

| 参数 | 含义 |
| --- | --- |
| `RULE_CONF_PERCENTILE` | 置信度百分位阈值 |
| `RULE_SUPP_PERCENTILE` | 支持度百分位阈值 |
| `RULE_STRENGTH_PERCENTILE` | 规则强度百分位阈值 |
| `RULE_RELAX_FACTOR` | 高质量规则不足时的阈值松弛因子 |

如果不设置这些环境变量，系统保持普通评测时的原有自适应阈值逻辑。

### 15.2 实验 A：百分位阈值敏感性

固定松弛因子为 `0.70`，改变三类百分位阈值：

| 组别 | conf | supp | strength | relax |
| --- | ---: | ---: | ---: | ---: |
| A1 | 0.70 | 0.70 | 0.80 | 0.70 |
| A2 | 0.75 | 0.75 | 0.85 | 0.70 |
| A3 | 0.80 | 0.80 | 0.90 | 0.70 |
| A4 | 0.85 | 0.85 | 0.95 | 0.70 |

运行实验 A：

```bash
python run_sensitivity_analysis.py --suite A
```

### 15.3 实验 B：松弛因子敏感性

固定百分位阈值为 `0.80/0.80/0.90`，改变松弛因子：

| 组别 | conf | supp | strength | relax |
| --- | ---: | ---: | ---: | ---: |
| B1 | 0.80 | 0.80 | 0.90 | 0.60 |
| B2 | 0.80 | 0.80 | 0.90 | 0.70 |
| B3 | 0.80 | 0.80 | 0.90 | 0.80 |
| B4 | 0.80 | 0.80 | 0.90 | 0.90 |

运行实验 B：

```bash
python run_sensitivity_analysis.py --suite B
```

### 15.4 输出文件

默认输出目录：

```text
test_results/sensitivity_analysis/
```

核心汇总文件：

```text
test_results/sensitivity_analysis/sensitivity_results.csv
```

每次评测的完整控制台日志保存在：

```text
test_results/sensitivity_analysis/logs/
```

CSV 中包含：

- 实验组编号
- 题型
- 地理领域
- 阈值参数
- 准确率
- 答对题数与总题数
- 平均规则数量
- 平均置信度、支持度、规则强度
- 松弛触发次数

### 15.5 常用运行方式

只跑单选：

```bash
python run_sensitivity_analysis.py --suite all --question-type single
```

只跑多选：

```bash
python run_sensitivity_analysis.py --suite all --question-type multiple
```

只跑某些领域：

```bash
python run_sensitivity_analysis.py --suite A --domains Climatology Hydrology SV
```

快速检查脚本流程，不建议作为正式结果：

```bash
python run_sensitivity_analysis.py --suite A --limit-runs 1
```

正式实验建议运行：

```bash
python run_sensitivity_analysis.py --suite all --question-type both --overwrite --use-backup-dicts
```

其中 `--overwrite` 表示覆盖旧的敏感性分析 CSV，`--use-backup-dicts` 表示使用 `dict_backup/` 中的干净词典，避免 DCR 历史写入词条影响阈值敏感性分析。

### 15.6 论文解释原则

敏感性分析必须固定题库、词典、关键词提取、概念格构建、规则生成、冗余消除和答案推理逻辑，仅改变阈值相关参数。论文中可用最高准确率和最低准确率之间的差值衡量鲁棒性；若平均准确率波动较小，且没有子领域出现明显下降，则说明 3WCA 规则筛选机制对参数扰动不敏感。

## 16. 常用命令汇总

单选普通评测：

```bash
python batch_evaluate.py single_questions/Soil_and_Vegetation.json \
  -d dict_single/SV.csv
```

单选 DCR：

```bash
python batch_evaluate.py single_questions/Soil_and_Vegetation.json \
  -d dict_single/SV.csv \
  --enable-dcr \
  --llm-provider deepseek
```

多选普通评测：

```bash
python batch_evaluate.py multiple_questions/Soil_and_Vegetation.json \
  -d dict_multiple/SV.csv
```

多选 DCR：

```bash
python batch_evaluate.py multiple_questions/Soil_and_Vegetation.json \
  -d dict_multiple/SV.csv \
  --enable-dcr \
  --llm-provider deepseek
```

使用干净备份词典：

```bash
cp dict_backup/dict_single/SV.csv dict_single/SV_dcr_test.csv

python batch_evaluate.py single_questions/Soil_and_Vegetation.json \
  -d dict_single/SV_dcr_test.csv \
  --enable-dcr \
  --llm-provider deepseek
```

全量 DCR：

```bash
python batch_evaluate.py single_questions/Soil_and_Vegetation.json \
  -d dict_single/SV.csv \
  --enable-dcr \
  --llm-provider deepseek \
  --dcr-target all
```

DCR 判题覆盖上限实验：

```bash
python batch_evaluate.py single_questions/Soil_and_Vegetation.json \
  -d dict_single/SV.csv \
  --enable-dcr \
  --llm-provider deepseek \
  --enable-dcr-answer-override
```

## 17. 系统局限性

- 静态词典质量仍然直接影响推理效果。
- DCR 依赖大模型，存在成本和稳定性问题。
- DCR 自动写词典可能带来词典污染，需要备份和审查。
- DCR 辅助判题覆盖可能提高明显，但必须作为单独的后验上限实验报告。
- 若要模拟真实部署，应更多使用 `--dcr-target all` 或提前固定增强策略。

## 18. 总结

本系统最初是一个基于静态词典、形式背景和三支概念分析的符号推理系统，优势是可解释性较强，但依赖人工词典。DCR 模块引入后，系统能够根据题目上下文动态补充缺失地理概念，并将大模型知识转化为可参与符号推理的结构化词典条目。

默认 DCR 评测不再让大模型直接覆盖答案，因此可以用于观察扩展词典对系统自身推理链的真实贡献。若进一步显式加入 DCR 辅助判题覆盖，应单独报告为“系统 + 大模型判题覆盖”的后验上限实验。
