import os
import json
import argparse
import sys
import re
from itertools import combinations

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

_JIEBA_READY = False
QUESTION_NOISE_WORDS = {
    "下列", "关于", "说法", "的是", "正确", "错误", "属于", "不属于",
    "包括", "不包括", "结合", "相关", "有", "无", "其中"
}
NEGATIVE_QUESTION_CUES = [
    "不正确", "错误的是", "错误的有", "不属于", "不包括", "不可能",
    "不能", "不利于", "不符合", "不合理", "不应", "不宜", "不具备"
]
ABSOLUTE_RISK_CUES = [
    "一定", "完全", "仅", "只", "直接决定", "无影响", "不会", "必然", "所有"
]

def _normalize_text(text):
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(text or ""))

def _split_text_fragments(text):
    cleaned_text = str(text or "").strip()
    if not cleaned_text:
        return []

    normalized = re.sub(r"[（）()【】\\[\\]]", " ", cleaned_text)
    parts = [cleaned_text]

    for chunk in re.split(r"[，,；;、。]", normalized):
        piece = chunk.strip(" ：: ")
        if len(piece) >= 2:
            parts.append(piece)
        for sub_piece in re.split(r"(?:和|及|与|并且|且|以及|或者|或)", piece):
            sub_piece = sub_piece.strip(" ：: ")
            if len(sub_piece) >= 2:
                parts.append(sub_piece)

    return _unique_terms(parts)

def _char_similarity(text_a, text_b):
    normalized_a = _normalize_text(text_a)
    normalized_b = _normalize_text(text_b)
    if not normalized_a or not normalized_b:
        return 0.0

    set_a = set(normalized_a)
    set_b = set(normalized_b)
    union = set_a | set_b
    if not union:
        return 0.0

    return len(set_a & set_b) / len(union)

def _soft_similarity(text_a, text_b, context_builder):
    if not text_a or not text_b:
        return 0.0

    normalized_a = _normalize_text(text_a)
    normalized_b = _normalize_text(text_b)
    if normalized_a and normalized_a == normalized_b:
        return 1.0

    contain_score = 0.0
    if normalized_a and normalized_b and (normalized_a in normalized_b or normalized_b in normalized_a):
        contain_score = min(len(normalized_a), len(normalized_b)) / max(len(normalized_a), len(normalized_b))

    token_score = context_builder.calculate_similarity(str(text_a), str(text_b))
    char_score = _char_similarity(text_a, text_b)
    return max(token_score, char_score, contain_score)

def _split_domain_values(text):
    if not text:
        return []
    return [
        item.strip()
        for item in str(text).replace("；", "、").replace(";", "、").split("、")
        if item.strip() and item.strip() != "nan"
    ]

def _unique_terms(values):
    seen = set()
    ordered = []
    for value in values:
        cleaned = str(value).strip()
        if not cleaned or cleaned == "nan" or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered

def _best_context_support(text, candidates, context_builder, min_similarity=0.28, top_k=3):
    similarities = []
    for candidate in candidates:
        sim = _soft_similarity(text, candidate, context_builder)
        if sim >= min_similarity:
            similarities.append(sim)

    if not similarities:
        return 0.0

    similarities.sort(reverse=True)
    top_scores = similarities[:top_k]
    weights = [1.0, 0.7, 0.5]
    weighted_sum = sum(score * weights[idx] for idx, score in enumerate(top_scores))
    return weighted_sum / sum(weights[:len(top_scores)])

def _option_related_terms(option_text, extractor):
    terms = _split_text_fragments(option_text)
    info = extractor.domain.get(option_text, {})
    if info:
        for value in _split_domain_values(info.get("上级", "")):
            terms.extend(_split_text_fragments(value))
        for value in _split_domain_values(info.get("下级", "")):
            terms.extend(_split_text_fragments(value))
    return _unique_terms(terms)

def _absolute_risk_penalty(option_text):
    text = str(option_text or "")
    hit_count = sum(cue in text for cue in ABSOLUTE_RISK_CUES)
    return 0.28 * hit_count

def _best_option_match(fragment, opts_dict, context_builder, min_similarity=0.30):
    best_label = None
    best_score = 0.0
    for label, option_text in opts_dict.items():
        score_candidates = [_soft_similarity(fragment, option_text, context_builder)]
        score_candidates.extend(
            _soft_similarity(fragment, fragment_piece, context_builder)
            for fragment_piece in _split_text_fragments(option_text)[1:]
        )
        score = max(score_candidates) if score_candidates else 0.0
        if score > best_score:
            best_label = label
            best_score = score

    if best_score >= min_similarity:
        return best_label, best_score

    return None, 0.0

def _map_conclusion_to_labels(conclusion, opts_dict, context_builder):
    cleaned_conclusion = str(conclusion).strip()
    if not cleaned_conclusion:
        return [], 0.0

    if '+' in cleaned_conclusion:
        matched_labels = []
        matched_scores = []
        used_labels = set()

        for part in [item.strip() for item in cleaned_conclusion.split('+') if item.strip()]:
            label, score = _best_option_match(part, opts_dict, context_builder, min_similarity=0.28)
            if not label or label in used_labels:
                return [], 0.0
            used_labels.add(label)
            matched_labels.append(label)
            matched_scores.append(score)

        return matched_labels, sum(matched_scores) / len(matched_scores)

    label, score = _best_option_match(cleaned_conclusion, opts_dict, context_builder, min_similarity=0.35)
    if not label:
        return [], 0.0

    return [label], score

def _score_options(stem, opts_dict, keywords, results, final_rules, extractor, context_builder):
    option_scores = {label: 0.0 for label in opts_dict.keys()}
    rule_scores = {label: 0.0 for label in opts_dict.keys()}
    direct_scores = {label: 0.0 for label in opts_dict.keys()}
    combo_scores = {}

    stem_fragments = _split_text_fragments(stem)
    keyword_terms = _unique_terms(keywords)
    attribute_terms = _unique_terms(results.get("attribute_set", []))
    object_terms = _unique_terms(results.get("object_set", []))
    evidence_terms = _unique_terms(keyword_terms + attribute_terms + object_terms)

    for label, option_text in opts_dict.items():
        option_related_terms = _option_related_terms(option_text, extractor)
        option_fragments = _split_text_fragments(option_text)[1:]
        domain_bridge_score = 0.0
        if option_related_terms:
            related_support = [
                _best_context_support(term, evidence_terms, context_builder, min_similarity=0.24, top_k=2)
                for term in option_related_terms
            ]
            domain_bridge_score = max(related_support) if related_support else 0.0

        keyword_bridge_score = 0.0
        if option_related_terms and keyword_terms:
            keyword_bridge_scores = [
                _best_context_support(term, keyword_terms, context_builder, min_similarity=0.24, top_k=2)
                for term in option_related_terms
            ]
            keyword_bridge_score = max(keyword_bridge_scores) if keyword_bridge_scores else 0.0

        stem_bridge_score = 0.0
        if option_related_terms and stem_fragments:
            stem_bridge_scores = [
                _best_context_support(term, stem_fragments, context_builder, min_similarity=0.24, top_k=2)
                for term in option_related_terms
            ]
            stem_bridge_score = max(stem_bridge_scores) if stem_bridge_scores else 0.0

        fragment_support = 0.0
        if option_fragments:
            fragment_scores = [
                _best_context_support(fragment, evidence_terms, context_builder, min_similarity=0.24, top_k=2)
                for fragment in option_fragments
            ]
            fragment_support = sum(fragment_scores) / len(fragment_scores)

        direct_score = 0.0
        direct_score += 1.10 * _best_context_support(option_text, keyword_terms, context_builder, min_similarity=0.24, top_k=2)
        direct_score += 1.00 * _best_context_support(option_text, attribute_terms, context_builder, min_similarity=0.24, top_k=3)
        direct_score += 0.75 * _best_context_support(option_text, object_terms, context_builder, min_similarity=0.24, top_k=3)
        direct_score += 0.85 * fragment_support
        direct_score += 0.95 * keyword_bridge_score
        direct_score += 0.95 * stem_bridge_score
        direct_score += 0.90 * domain_bridge_score
        direct_score += 0.20 * _soft_similarity(option_text, stem, context_builder)
        direct_score -= _absolute_risk_penalty(option_text)

        direct_scores[label] = direct_score
        option_scores[label] += direct_score

    for rule in final_rules or []:
        strength = max(float(rule.get("rule_strength", 0) or 0), 0.0)
        if strength <= 0:
            continue

        for conclusion in rule.get("conclusion_names", []):
            matched_labels, match_score = _map_conclusion_to_labels(conclusion, opts_dict, context_builder)
            if not matched_labels:
                continue

            contribution = strength * match_score
            if len(matched_labels) == 1:
                label = matched_labels[0]
                rule_scores[label] += contribution
                option_scores[label] += contribution
                continue

            label_set = frozenset(matched_labels)
            combo_scores[label_set] = combo_scores.get(label_set, 0.0) + contribution
            shared_contribution = contribution * (0.90 if len(label_set) >= 3 else 0.75) / len(label_set)
            for label in matched_labels:
                rule_scores[label] += shared_contribution
                option_scores[label] += shared_contribution

    return option_scores, direct_scores, rule_scores, combo_scores

def _predict_single_answer(option_scores, direct_scores, opts_dict, prefer_low_score=False):
    if not option_scores:
        return []

    chooser = min if prefer_low_score else max
    best_label = chooser(
        opts_dict.keys(),
        key=lambda label: (option_scores.get(label, 0.0), direct_scores.get(label, 0.0), label)
    )
    return [best_label]

def _is_negative_question(stem):
    normalized_stem = re.sub(r"\s+", "", str(stem or ""))
    return any(cue in normalized_stem for cue in NEGATIVE_QUESTION_CUES)

def _refine_keywords(keywords):
    refined = [kw for kw in keywords if str(kw).strip() and str(kw).strip() not in QUESTION_NOISE_WORDS]
    return refined if refined else keywords

def _predict_multiple_answers(option_scores, direct_scores, combo_scores, opts_dict):
    if not option_scores:
        return []

    labels = list(opts_dict.keys())
    ranked_labels = sorted(labels, key=lambda label: (option_scores.get(label, 0.0), label), reverse=True)
    max_score = max(option_scores.values()) if option_scores else 0.0
    if max_score <= 0:
        return [ranked_labels[0]] if ranked_labels else []

    normalized_scores = {label: option_scores[label] / max_score for label in labels}
    top_scores = [normalized_scores[label] for label in ranked_labels]
    top1 = top_scores[0] if len(top_scores) > 0 else 0.0
    top2 = top_scores[1] if len(top_scores) > 1 else 0.0
    top3 = top_scores[2] if len(top_scores) > 2 else 0.0

    direct_max_score = max(direct_scores.values()) if direct_scores else 0.0
    direct_min_score = min(direct_scores.values()) if direct_scores else 0.0
    if direct_max_score > 1.0 and direct_min_score / direct_max_score >= 0.80:
        return sorted(labels)

    all_labels_set = frozenset(labels)
    triple_combo_score = combo_scores.get(all_labels_set, 0.0)

    best_pair = None
    best_pair_combo_score = 0.0
    for pair in combinations(labels, 2):
        pair_set = frozenset(pair)
        pair_combo_score = combo_scores.get(pair_set, 0.0)
        if pair_combo_score > best_pair_combo_score:
            best_pair_combo_score = pair_combo_score
            best_pair = list(pair)

    if triple_combo_score >= max(best_pair_combo_score * 1.15, max_score * 0.30):
        selected = [label for label in labels if normalized_scores[label] >= 0.58]
        return sorted(selected or labels)

    if top3 >= 0.93 and top2 >= 0.96 and abs(top1 - top3) <= 0.08:
        selected = [label for label in labels if normalized_scores[label] >= 0.58]
        return sorted(selected)

    if best_pair:
        outside_labels = [label for label in labels if label not in best_pair]
        outside_score = normalized_scores[outside_labels[0]] if outside_labels else 0.0
        pair_floor = min(normalized_scores[label] for label in best_pair)
        if best_pair_combo_score >= max_score * 0.18 and pair_floor >= 0.45 and pair_floor - outside_score >= 0.05:
            return sorted(best_pair)

    if top2 >= 0.58 and (top2 - top3 >= 0.10 or top3 <= 0.48):
        return sorted(ranked_labels[:2])

    strong_labels = [label for label in labels if normalized_scores[label] >= 0.68]
    if len(strong_labels) >= 2:
        return sorted(strong_labels)

    return [ranked_labels[0]]

def evaluate_json(json_path, custom_dict=None):
    global _JIEBA_READY
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
    if not _JIEBA_READY:
        jieba.add_word('西高东低', freq=1000, tag='n')
        _JIEBA_READY = True
    
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

        if isinstance(correct_answer, str):
            correct_answer = [correct_answer.strip()] if correct_answer.strip() else []
        elif isinstance(correct_answer, list):
            correct_answer = [str(x).strip() for x in correct_answer if str(x).strip()]
        else:
            correct_answer = []

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
            kws = _refine_keywords(extractor.extract_keywords(stem, top_k=10))
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
            final_rules = extract_three_way_rules_enhanced.main() or []

            print(f"\n--- 第 {idx} 题流程闭环正常结束 ---")
            
            option_scores, direct_scores, rule_scores, combo_scores = _score_options(
                stem,
                opts_dict,
                kws,
                results,
                final_rules,
                extractor,
                context_builder,
            )

            question_type = str(q_info.get("type", "")).strip().lower()
            if question_type == "multiple":
                predicted_answer = _predict_multiple_answers(option_scores, direct_scores, combo_scores, opts_dict)
            else:
                predicted_answer = _predict_single_answer(
                    option_scores,
                    direct_scores,
                    opts_dict,
                    prefer_low_score=_is_negative_question(stem),
                )

            correct_answer_sorted = sorted(correct_answer)
            is_correct = (predicted_answer == correct_answer_sorted)
            if is_correct:
                correct_count += 1
            
            print(f"[*] 系统预测选项: {predicted_answer} | 实际正确选项: {correct_answer_sorted} | 此题{'准确' if is_correct else '错误'}")
            print(f"    选项得分: { {k: round(v, 3) for k, v in option_scores.items()} }")
            
            # 记录当前题目的解题结果
            all_results_summary.append({
                "question_id": q_info.get("id"),
                "category": q_info.get("geography_category"),
                "question": stem,
                "options": opts_dict,
                "correct_answer": correct_answer,
                "predicted_answer": predicted_answer,
                "is_correct": is_correct,
                "option_scores": {k: round(v, 6) for k, v in option_scores.items()},
                "direct_scores": {k: round(v, 6) for k, v in direct_scores.items()},
                "rule_scores": {k: round(v, 6) for k, v in rule_scores.items()},
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
            f.write(f"     选项得分: {res['option_scores']}\n")
            f.write(f"     直接证据得分: {res['direct_scores']}\n")
            f.write(f"     规则证据得分: {res['rule_scores']}\n")
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
    return {
        "json_path": json_path,
        "total_count": total_count,
        "correct_count": correct_count,
        "accuracy": (correct_count / total_count) if total_count > 0 else 0.0,
        "results": all_results_summary,
    }

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
