import os
import json
import argparse
import sys

# 导入自定义模块
from geo_keyword_extractor import GeoKeywordExtractor
from entity_attribute import EntityAttributeExtractor
from formal_context_builder import FormalContextBuilder
import jieba

# 导入5个串联流程的脚本模块作为包
import threeWcl
import process_result_decision
import merge_concepts
import extract_three_way_rules_enhanced

def evaluate_json(json_path, custom_dict=None):
    print("="*70)
    print(f"【批量处理模式启动】目标文件: {json_path}")
    print("="*70)

    # 读取 JSON 文件
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"读取文件失败: {e}")
        return
        
    questions = data.get("geography_questions", [])
    if not questions:
        print("未在文件中找到 geography_questions 列表！")
        return

    # [优化点1]：全局只初始化1次高开销模型
    print(">>> 正在加载结巴分词与词典缓存（仅加载一次）...")
    jieba.add_word('西高东低', freq=1000, tag='n')
    
    syn_path = "geo_synonyms.csv"
    
    # 支持自定义选择词典
    if custom_dict and os.path.exists(custom_dict):
        domain_path = custom_dict
    else:
        # 动态根据当前题型判断所用字典（后备默认逻辑）
        if "single_" in os.path.basename(json_path):
            domain_path = "单选词典.csv"
        else:
            domain_path = "多选词典.csv"
            
        if not os.path.exists(domain_path):
            domain_path = "多选词典.csv" # 兜底逻辑
        
    print(f">>> 使用领域词典: {domain_path}")
    
    # 初始化核心特征提取器
    extractor = GeoKeywordExtractor(domain_csv=domain_path, synonym_csv=syn_path)
    context_builder = EntityAttributeExtractor(extractor)

    correct_count = 0
    total_count = len(questions)
    
    # 汇总所有题目的生成规则信息
    all_results_summary = []

    # 循环遍历解答题目
    for idx, q_info in enumerate(questions, start=1):
        print("\n\n" + "#"*70)
        print(f"正在分析第 {idx}/{total_count} 题 (ID: {q_info.get('id', 'N/A')}) - 类别: {q_info.get('geography_category')}")
        print("#"*70)

        stem = q_info["question"]
        opts_dict = q_info.get("options", {})
        # 提取选项值（仅文本内容）
        options = [v for k, v in opts_dict.items()]
        correct_answer = q_info.get("correct_answer", [])

        print(f"【题干】: {stem}")
        print(f"【选项】: {options}")
        print(f"【参考答案】: {correct_answer}")

        # 【防止残存污染】每次循环第一步清理旧文件
        import glob
        for f in glob.glob("test_contexts/*.txt") + glob.glob("test_contexts/*.csv") + glob.glob("test_results/*.txt"):
            if "batch_evaluation_summary" not in f:
                try: os.remove(f)
                except: pass

        try:
            # 步骤1：主控信息抽取（原main.py逻辑）
            kws = extractor.extract_keywords(stem, top_k=10)
            print(">>> 题干提权关键词：", kws)
            results = context_builder.build_entity_relations_and_attributes(kws, options)
            
            # 构建形式背景并在本地暂存 0-1 矩阵（给后续流程使用）
            formal_builder = FormalContextBuilder(results)
            formal_builder.build_and_save_contexts(extractor, "decision_formal_context")
            
            # 步骤2：三支概念网格生成计算
            # 已经修复了 threeWcl 中的绝对路径硬盘硬编码问题
            print("\n>>> 开始执行概念计算 (threeWcl.py)...")
            threeWcl.threeWcl()
            
            # 步骤3：决策结果偏移处理
            print("\n>>> 开始处理决策偏移 (process_result_decision.py)...")
            processed_file = os.path.join('test_results', 'threeWcl_decision.txt')
            process_result_decision.process_file(processed_file)
            
            # 步骤4：概念合并交集
            print("\n>>> 开始合并概念格 (merge_concepts.py)...")
            merge_concepts.main()
            
            # 步骤5：增强版规则提取
            print("\n>>> 增强规则提取和答案推断 (extract_three_way_rules_enhanced.py)...")
            final_rules = extract_three_way_rules_enhanced.main()

            print(f"\n--- 第 {idx} 题流程闭环正常结束 ---")
            
            # 自动化预测推断 (Inference Module)
            predicted_answer = []
            if final_rules:
                vote_scores = {k: 0.0 for k in opts_dict.keys()}
                for rule in final_rules:
                    conclusions = rule.get('conclusion_names', [])
                    strength = rule.get('rule_strength', 0)
                    for conclude_item in conclusions:
                        parts = [p.strip() for p in conclude_item.split('+')]
                        for part in parts:
                            for k, v in opts_dict.items():
                                if part == v or part in v or v in part:
                                    vote_scores[k] += strength
                                else:
                                    # 基于分词的语义重合度
                                    sim = context_builder.calculate_similarity(part, v)
                                    # 基于字符级别的重合度（特别是对于中文）
                                    char_sim = len(set(part) & set(v)) / len(set(part) | set(v)) if (set(part) | set(v)) else 0
                                    
                                    best_sim = max(sim, char_sim)
                                    if best_sim > 0.05: # 降低相似度门槛以便命中
                                        vote_scores[k] += strength * best_sim
                
                if sum(vote_scores.values()) > 0:
                    max_score = max(vote_scores.values())
                    predicted_answer = [k for k, v in vote_scores.items() if v == max_score and v > 0]
            predicted_answer.sort()
            
            correct_answer_sorted = sorted(correct_answer)
            is_correct = (predicted_answer == correct_answer_sorted)
            if is_correct:
                correct_count += 1
            
            print(f"[*] 系统预测选项: {predicted_answer} | 实际正确选项: {correct_answer_sorted} | 此题{'准确' if is_correct else '错误'}")
            
            # 记录当前题目的解题结果
            all_results_summary.append({
                "question_id": q_info.get("id"),
                "category": q_info.get("geography_category"),
                "question": stem,
                "options": opts_dict,
                "correct_answer": correct_answer,
                "predicted_answer": predicted_answer,
                "is_correct": is_correct,
                "extracted_rules_count": len(final_rules) if final_rules else 0,
                "rules": final_rules
            })
            
        except Exception as e:
            print(f"\n!!! 第 {idx} 题解析出错，跳过该题。错误详情: {str(e)} !!!")

    print("\n" + "="*70)
    print(f"批处理完成！共执行 {total_count} 道题目。")
    print(f"系统答对 {correct_count} 道题。整体准确率: {(correct_count/total_count)*100 if total_count > 0 else 0:.2f}%")
    print("="*70)
    
    # 最终输出一个大汇总文件
    output_summary_path = os.path.join("test_results", "batch_evaluation_summary.txt")
    os.makedirs("test_results", exist_ok=True)
    with open(output_summary_path, "w", encoding="utf-8") as f:
        f.write("=== 批处理统一结果汇总 ===\n")
        f.write(f"测试文件: {json_path}\n")
        f.write(f"测试题数: {total_count}\n")
        f.write(f"答对题数: {correct_count}\n")
        f.write(f"整体准确率: {(correct_count/total_count)*100 if total_count > 0 else 0:.2f}%\n\n")
        
        for res in all_results_summary:
            f.write(f"[{res['question_id']}] 题目: {res['question']}\n")
            opts_str = ", ".join([f"{k}: {v}" for k, v in res['options'].items()])
            f.write(f"     选项: {opts_str}\n")
            f.write(f"     正确答案: {res['correct_answer']}\n")
            f.write(f"     预测答案: {res['predicted_answer']}  {'[正确]' if res['is_correct'] else '[错误]'}\n")
            f.write(f"     生成的规则数: {res['extracted_rules_count']}\n")
            if res['rules']:
                for r_idx, rule in enumerate(res['rules'], 1):
                    # 修改：同时输出规则名字供人理解
                    premise = ', '.join(rule.get('premise_names', []))
                    conclusion = ', '.join(rule.get('conclusion_names', []))
                    conf = rule.get('confidence', 0)
                    strength = rule.get('rule_strength', 0)
                    f.write(f"       规则 {r_idx}: {{{premise}}} → {{{conclusion}}} (置信度: {conf:.3f}, 强度: {strength:.3f})\n")
            f.write("-" * 50 + "\n")
            
    print(f"所有题目的综合分析报告已保存至 {output_summary_path} ！")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="一键批量测试题库并验证准确率")
    parser.add_argument("json_file", nargs='?', default=None, help="题目JSON文件路径")
    parser.add_argument("-d", "--dict", default=None, help="可选：指定要使用的领域词典文件路径 (例如: single_dictionary/dic1.csv)")
    args = parser.parse_args()

    if args.json_file and os.path.exists(args.json_file):
        evaluate_json(args.json_file, custom_dict=args.dict)
    else:
        print("请提供有效的 JSON 文件路径。")
        print("示例语法：python batch_evaluate.py single_questions/single_Climatology.json -d dic_all/dic_all_single_multiple.csv")
