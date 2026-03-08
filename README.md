# Automated GMCQs Answering System (高中地理多项选择题自动化问答系统)

[English](#-english-version) | [中文说明](#-中文版-chinese-version)

---

## 🇬🇧 English Version

### 📖 Introduction
This project aims to build an intelligent closed-loop system capable of automatically understanding, reasoning, and answering high school geography multiple-choice questions (applicable to single and multiple choices). 
The system is based on **Natural Language Processing (NLP)** and **Three-way Concept Lattices** theory. It extracts geographic features from question stems, constructs a decision formal context matrix using a domain-specific dictionary, deduces high-confidence geographic rules via three-way concept lattice algorithms, and finally performs semantic mapping against options to achieve fully automated answer inference.

### 💻 System Interface
Below are the system's operational and reasoning interface demonstrations:

#### Interface 1: Dashboard & Overview
![System Interface 1](interface_photo/interface1.png)

#### Interface 2: Question Bank Import & Processing
![System Interface 2](interface_photo/interface2.png)

#### Interface 3: Knowledge Graph & Concept Lattice
![System Interface 3](interface_photo/interface3.png)

#### Interface 4: Rule Extraction & Traceability
![System Interface 4](interface_photo/interface4.png)

### ⚙️ Architecture & Pipeline
The entire project is orchestrated by the master controller `batch_evaluate.py` for fully automated batch processing:

1. **Geographic Feature Extraction (`geo_keyword_extractor.py`, `entity_attribute.py`)**: Uses `jieba` and TextRank to process question texts, force-mapping features to the built-in domain dictionary to capture hierarchical and peer relationships of geographic entities.
2. **Formal Context Generation (`formal_context_builder.py`)**: Constructs a standard binary (0,1) Decision Formal Context Matrix based on keyword association sets and options.
3. **Three-way Concept Lattice Calculation (`threeWcl.py`, `util/CL.py`)**: Applies three-way decision operations on condition and decision domains, generating underlying concept models.
4. **Decision Result Processing & Merging (`process_result_decision.py`, `merge_concepts.py`)**: Handles dimensional offsets of model computations and extracts concept lattice intersections to form high-matching object sets.
5. **Intelligent Rule Extraction & Auto-Inference (`extract_three_way_rules_enhanced.py`)**: Filters valid geographic rules (e.g., `[Karst feature, Stone forest] -> [Cave]`) based on Confidence, Support, and Rule Strength. The inference layer scores these rules using a dual-mode matching mechanism (character overlap + semantic intersection) to predict the best answer (A/B/C/D) and auto-generates prediction accuracy %.

### 🚀 Quick Start

#### 1. Environment Setup
Please ensure you are using Python 3 and install the required packages:
```bash
pip install pandas numpy jieba
```

#### 2. Execute Batch Evaluation
Use the command line to start the main controller, specifying the JSON question bank and dictionary:
```bash
# Example: Evaluate Climatology single questions using the combined dictionary
python batch_evaluate.py single_questions/single_Climatology.json -d dic_all/dic_all_single_multiple.csv
```

#### 3. View the Analysis Report
After completion, the engine outputs a detailed execution report in `/test_results/batch_evaluation_summary.txt`, which includes:
* Question stems and options
* Comparison between Correct Answers vs. System Predicted Answers
* Extracted Rule chains with Confidence and Inference Strength
* Overall Accuracy (%) mapping.

### 📁 Directory Layout

```text
├── batch_evaluate.py           # Core orchestrator / execution pipeline
├── single_questions/           # Structured JSON sources for single-choice questions
├── multiple_questions/         # Structured JSON sources for multiple-choice questions
├── dic_all/                    # Standardized high school geography domain mappings (.csv)
├── test_results/               # Auto-inference reports and intermediate rule logs
├── test_contexts/              # Temporary matrices for decision formal contexts
├── interface_photo/            ![System interface screenshots]
├── CHANGELOG.md                # Update history and refactoring logs
├── README.md                   # Project documentation
└── util/                       # Underlying lattice matrix calculation assets
```

---

## 🇨🇳 中文版 (Chinese Version)

# 高中地理多项选择题自动化问答系统 
**(Automated GMCQs Answering System)**

## 📖 项目简介 (Introduction)
本项目旨在建立一个能够自动理解、推理并作答“高中地理选择题（单选/多选）”的智能闭环系统。
系统基于**自然语言处理（NLP）**与**三支形式概念分析（Three-way Concept Lattices）**理论，通过提取题干中的地理特征、查询领域词典构建决策形式背景矩阵，再依托三支概念格算法推导出高置信度的地理规则，最终与选项进行语义比对，实现全自动的答案推断（Inference）。

## 💻 系统界面演示 (System Interface)

以下为本自动解答系统的操作与推理界面设计图演示：

### 系统界面 1：主控与大屏概览
![系统界面1](interface_photo/interface1.png)

### 系统界面 2：导入题库与解答处理
![系统界面2](interface_photo/interface2.png)

### 系统界面 3：知识图谱与概念格展示
![系统界面3](interface_photo/interface3.png)

### 系统界面 4：规则提取与依据回溯
![系统界面4](interface_photo/interface4.png)

## ⚙️ 核心流程体系 (Architecture & Pipeline)

项目目前已全部集成在主控调度器 `batch_evaluate.py` 进行全自动串联批处理：

1. **地理特征提取 (`geo_keyword_extractor.py`, `entity_attribute.py`)**：
   使用 `jieba` 分词及 TextRank 算法初步处理题干文本，将特征强制约束/映射至系统内置的领域词典中，抓取地理实体的上下级关系和同级属性。
2. **形式背景生成 (`formal_context_builder.py`)**：
   根据题干关键词关联集与选项，构造出一个标准的二元(0,1)条件-决策矩阵（Decision Formal Context Matrix）。
3. **三支概念格计算 (`threeWcl.py`, `util/CL.py`)**：
   采用三支决策运算条件正域与负域概念，生成底层的 `condition` 与 `decision` 模型。
4. **决策结果处理与合并 (`process_result_decision.py`, `merge_concepts.py`)**：
   处理模型运算的维度偏移并提取概念格交集，形成包含所有知识关系的高匹配度对象集合。
5. **智能规则提取与全自动推断 (`extract_three_way_rules_enhanced.py`)**：
   从底层统计中抽取置信度（Confidence）、支持度（Support）和规则强度均达标的地理规则（例如：`[喀斯特特征, 石林] -> [溶洞]`）。推断层会对这些规则使用“字符重合度+语义交集双模计算”机制进行相似度评分，智能推断选出最佳的答案选项(A/B/C/D)并自动统计**系统答对率**。

## 🚀 快速开始 (Quick Start)

### 1. 环境依赖安装
请确保您处于 Python 3 环境下：
```bash
pip install pandas numpy jieba
```

### 2. 执行批量评估系统
使用命令行启动主干控制器，您可以指定题库 JSON 以及地理专用大词典：
```bash
# 以评估气候单选题、并挂载合并词典为例：
python batch_evaluate.py single_questions/single_Climatology.json -d dic_all/dic_all_single_multiple.csv
```

### 3. 查看自动分析报告
测试完毕后，系统会在 `/test_results/batch_evaluation_summary.txt` 中输出测试战报结果，格式如下：
* 题目题干与选项集
* 正确答案与预测答案比对（错误/正确标红提示）
* 成功提取出的每一条三支推理规则（及其置信度和综合推断强度）
* 整个 JSON 测试集的整体准确率 (Accuracy %)。

## 📁 目录结构 (Directory Layout)

```text
├── batch_evaluate.py           # 核心控制/调度程序：执行流水线计算与自动推导
├── single_questions/           # 将单选题库结构化改写的 JSON 数据源 
├── multiple_questions/         # 将多选题库结构化改写的 JSON 数据源 
├── dic_all/                    # 规范化的高中地理领域映射词典库 (csv格式)
├── test_results/               # 中间算法文本留存 及 详细的评估摘要报告汇总
├── test_contexts/              # 前置计算的决策形式背景矩阵暂存区
├── interface_photo/            ![系统界面图集文件夹]
├── CHANGELOG.md                # 系统迭代与重构更新日志
├── README.md                   # 项目说明与指引文档
└── util/                       # 底层三支概念格矩阵算子库
```