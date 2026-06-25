import os
import json
import argparse
import sys
import re
from itertools import combinations
import pandas as pd

# 导入自定义模块
from geo_keyword_extractor import GeoKeywordExtractor
from geo_keyword_extractor_dcr_integration import create_extractor_with_dcr
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
QUESTION_GENERIC_WORDS = {
    "一个", "一种", "一定", "主要", "同时", "能够", "可以", "进行", "通过",
    "由于", "因此", "因为", "所以", "形成", "影响", "决定", "因素", "多种",
    "不同", "直接", "间接", "表现", "体现", "具有", "没有", "比较", "分析",
    "判断", "选择", "说明", "可能", "最可能", "最主要", "过程中", "地区",
    "区域", "环境", "条件", "特点", "变化", "差异", "作用", "关系", "导致",
    "增加", "减少", "提高", "降低", "较高", "较低", "较大", "较小", "明显",
    "适合", "不适合", "合理", "不合理", "正确", "错误", "正确的是", "错误的是",
    "根据", "当地", "中部", "东部", "西部", "南部", "北部", "海岸", "沿海",
    "高低", "组成部分", "密切相关", "变化规律", "覆盖率"
}
GEOGRAPHIC_HINT_CHARS = set(
    "土壤植被森林草原荒漠沙漠湿地苔原针叶阔叶灌丛乔木草本根系腐殖质有机质"
    "水热温降雨径流河湖海洋冰川地形地貌山地高原平原盆地丘陵坡向海拔纬度经度"
    "气候季风干旱湿润盐碱酸性碱性中性肥力养分质地淋溶侵蚀沉积风化成土"
)
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

def _is_good_dcr_candidate(term):
    text = str(term or "").strip()
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if text in QUESTION_NOISE_WORDS or text in QUESTION_GENERIC_WORDS:
        return False
    if normalized.isdigit():
        return False
    if len(normalized) < 2 or len(normalized) > 24:
        return False
    if re.fullmatch(r"[A-Za-z0-9]+", normalized):
        return False
    if any(ch in text for ch in "（）()，,。；;：:"):
        return False
    if len(normalized) == 2 and not (set(normalized) & GEOGRAPHIC_HINT_CHARS):
        return False
    return True

def _clear_keyword_extractor_cache(domain_path):
    GeoKeywordExtractor._domain_cache.pop(domain_path, None)

def _resolve_domain_path(json_path, custom_dict=None):
    if custom_dict:
        if os.path.exists(custom_dict):
            return custom_dict
        raise FileNotFoundError(
            f"指定的词典文件不存在: {custom_dict}\n"
            f"请先创建该文件，或改用已有词典路径，例如 dict_multiple/SV.csv。"
        )

    filename = os.path.basename(json_path).lower().replace(" ", "_")
    is_single = "single" in os.path.dirname(json_path).lower() or filename.startswith("single")
    dict_dir = "dict_single" if is_single else "dict_multiple"
    category_map = {
        "climatology": "Climatology.csv",
        "hydrology": "Hydrology.csv",
        "soil_and_vegetation": "SV.csv",
        "topography_and_geomorphology": "TG.csv",
        "human_and_economic_geography": "HEG.csv",
        "geographical_processes_and_principles": "GPP.csv",
    }

    for marker, dict_name in category_map.items():
        if marker in filename:
            inferred_path = os.path.join(dict_dir, dict_name)
            if os.path.exists(inferred_path):
                return inferred_path

    fallback = os.path.join(dict_dir, "Climatology.csv")
    if os.path.exists(fallback):
        return fallback
    raise FileNotFoundError(f"无法为题库自动推断词典，请使用 -d 显式指定词典文件: {json_path}")

def _load_geography_questions(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data, data.get("geography_questions", [])

def _write_geography_questions(json_path, questions):
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"geography_questions": questions}, f, ensure_ascii=False, indent=2)

def _build_llm_config(provider=None, model=None, api_key=None):
    provider = (provider or "").strip().lower()
    if not provider:
        if os.environ.get("DEEPSEEK_API_KEY"):
            provider = "deepseek"
        elif os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        else:
            provider = "local"

    env_keys = {
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    default_models = {
        "deepseek": "deepseek-chat",
        "openai": "gpt-3.5-turbo",
        "anthropic": "claude-3-opus-20240229",
        "local": "qwen2",
    }

    config = {
        "provider": provider,
        "model": model or default_models.get(provider, default_models["local"]),
    }
    resolved_key = api_key or os.environ.get(env_keys.get(provider, ""), "")
    if resolved_key:
        config["api_key"] = resolved_key
    return config

def _validate_llm_config_for_dcr(llm_config):
    provider = llm_config.get("provider")
    if provider in {"deepseek", "openai", "anthropic"} and not llm_config.get("api_key"):
        env_key = {
            "deepseek": "DEEPSEEK_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }[provider]
        raise ValueError(
            f"{provider} 需要 API Key。请先设置环境变量 {env_key}，"
            f"或在命令中添加 --api-key。"
        )

def _is_climatology_category(category):
    category_text = str(category or "").lower()
    return "climatology" in category_text or "气候" in category_text or "气象" in category_text

def _predict_multiple_answers(option_scores, direct_scores, combo_scores, opts_dict, category=None):
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
    top_labels = ranked_labels[:3]

    direct_max_score = max(direct_scores.values()) if direct_scores else 0.0
    direct_min_score = min(direct_scores.values()) if direct_scores else 0.0
    direct_ranked = sorted(labels, key=lambda label: (direct_scores.get(label, 0.0), label), reverse=True)
    direct_top = direct_scores.get(direct_ranked[0], 0.0) if direct_ranked else 0.0
    direct_third = direct_scores.get(direct_ranked[2], 0.0) if len(direct_ranked) >= 3 else 0.0
    direct_third_ratio = direct_third / direct_top if direct_top > 0 else 0.0
    score_spread = top1 - top3
    is_true_three_way_tie = (
        len(labels) >= 3
        and top3 >= 0.92
        and score_spread <= 0.08
        and direct_third_ratio >= 0.88
    )

    if direct_max_score > 1.0 and direct_min_score / direct_max_score >= 0.92 and is_true_three_way_tie:
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

    if triple_combo_score >= max(best_pair_combo_score * 1.25, max_score * 0.35) and is_true_three_way_tie:
        return sorted(labels)

    if is_true_three_way_tie:
        return sorted(labels)

    if _is_climatology_category(category) and len(labels) >= 3:
        climatology_all_supported = (
            top3 >= 0.75
            and score_spread <= 0.25
            and direct_third_ratio >= 0.70
        )
        if climatology_all_supported:
            return sorted(labels)

    if best_pair:
        outside_labels = [label for label in labels if label not in best_pair]
        outside_score = normalized_scores[outside_labels[0]] if outside_labels else 0.0
        pair_floor = min(normalized_scores[label] for label in best_pair)
        if best_pair_combo_score >= max_score * 0.18 and pair_floor >= 0.45 and pair_floor - outside_score >= 0.05:
            return sorted(best_pair)

    if top2 >= 0.58 and (top2 - top3 >= 0.08 or top3 <= 0.62):
        return sorted(ranked_labels[:2])

    strong_labels = [label for label in labels if normalized_scores[label] >= 0.72]
    if len(strong_labels) >= 2:
        if len(strong_labels) == 3 and not is_true_three_way_tie:
            return sorted(ranked_labels[:2])
        return sorted(strong_labels)

    if len(top_labels) >= 2 and top2 >= 0.68:
        return sorted(top_labels[:2])

    return [ranked_labels[0]]

def evaluate_json(json_path, custom_dict=None, answer_overrides=None):
    global _JIEBA_READY
    answer_overrides = answer_overrides or {}
    print("="*70)
    print(f"【批量处理模式启动】目标文件: {json_path}")
    print("="*70)

    try:
        _, questions = _load_geography_questions(json_path)
    except Exception as e:
        print(f"读取文件失败: {e}")
        return

    if not questions:
        print("未在文件中找到 geography_questions 列表！")
        return

    # [优化点1]：全局只初始化1次高开销模型
    print(">>> 正在加载结巴分词与词典缓存（仅加载一次）...")
    if not _JIEBA_READY:
        jieba.add_word('西高东低', freq=1000, tag='n')
        _JIEBA_READY = True
    
    syn_path = "geo_synonyms.csv"
    
    domain_path = _resolve_domain_path(json_path, custom_dict)
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
            override_answer = answer_overrides.get(str(q_info.get("id")))
            prediction_source = "symbolic_system"
            if override_answer:
                predicted_answer = sorted(override_answer)
                prediction_source = "dcr_answer_override"
                print(f"[*] 使用DCR辅助判题覆盖预测: {predicted_answer}")
            elif question_type == "multiple":
                predicted_answer = _predict_multiple_answers(
                    option_scores,
                    direct_scores,
                    combo_scores,
                    opts_dict,
                    category=q_info.get("geography_category"),
                )
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
                "prediction_source": prediction_source,
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
            f.write(f"     预测来源: {res.get('prediction_source', 'symbolic_system')}\n")
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

def _detect_missing_terms_by_question(json_path, domain_path, allowed_question_ids=None):
    _, questions = _load_geography_questions(json_path)
    allowed_question_ids = set(allowed_question_ids) if allowed_question_ids is not None else None
    extractor = create_extractor_with_dcr(
        domain_csv=domain_path,
        synonym_csv="geo_synonyms.csv" if os.path.exists("geo_synonyms.csv") else None,
        enable_dcr=False,
    )

    records = []
    unique_terms = []
    seen_terms = set()
    contexts_by_term = {}
    for index, question in enumerate(questions, start=1):
        if allowed_question_ids is not None and question.get("id") not in allowed_question_ids:
            continue
        stem = question.get("question", "")
        options = question.get("options", {}) or {}
        combined_text = "。".join([stem] + [str(value) for value in options.values()])
        missing_terms = [
            term for term in extractor.detect_missing_keywords(combined_text)
            if _is_good_dcr_candidate(term)
        ]
        missing_terms = _unique_terms(missing_terms)
        if not missing_terms:
            continue

        option_text = "；".join(f"{label}. {value}" for label, value in options.items())
        for term in missing_terms:
            if term not in seen_terms:
                seen_terms.add(term)
                unique_terms.append(term)
            contexts_by_term.setdefault(term, []).append({
                "question_index": index,
                "question_id": question.get("id"),
                "question": stem,
                "options": option_text,
            })

        records.append({
            "question_index": index,
            "question_id": question.get("id"),
            "question": stem,
            "missing_terms": missing_terms,
        })

    return records, unique_terms, questions, contexts_by_term

def _sample_domain_entries(domain_path, limit=12):
    try:
        df = pd.read_csv(domain_path, encoding="utf-8")
    except Exception:
        return []

    examples = []
    for _, row in df.head(limit * 4).iterrows():
        keyword = str(row.get("关键字", "")).strip()
        category = str(row.get("分类", "")).strip()
        parent = str(row.get("上级", "")).strip()
        child = str(row.get("下级", "")).strip()
        if keyword and keyword != "nan" and category and category != "nan":
            examples.append(f"{keyword} | {category} | 上级:{parent} | 下级:{child}")
        if len(examples) >= limit:
            break
    return examples

def _build_term_context(term, contexts_by_term, domain_examples):
    contexts = contexts_by_term.get(term, [])[:2]
    parts = [
        "任务: 为地理试题词典补充概念关系。请优先给出能帮助选项判断的上级/下级或相关概念。",
        f"待补充术语: {term}",
    ]
    if domain_examples:
        parts.append("当前词典示例:")
        parts.extend(domain_examples[:8])
    for item in contexts:
        parts.append(f"题目ID: {item.get('question_id')}")
        parts.append(f"题干: {item.get('question')}")
        parts.append(f"选项: {item.get('options')}")
    return "\n".join(parts)

def _retrieve_missing_terms_with_context(dcr_extractor, terms, contexts_by_term, domain_path):
    domain_examples = _sample_domain_entries(domain_path)
    results = {}
    if not dcr_extractor.dcr:
        return results

    for index, term in enumerate(terms, start=1):
        if index == 1 or index % 10 == 0:
            print(f">>> DCR进度: {index}/{len(terms)}")
        context = _build_term_context(term, contexts_by_term, domain_examples)
        entry = dcr_extractor.dcr.retrieve_concept(term, context=context)
        results[term] = entry
        if entry:
            dcr_extractor._record_missing(term, entry)
    return results

def _build_records_for_question_ids(questions, question_ids):
    question_ids = set(question_ids or [])
    records = []
    for index, question in enumerate(questions, start=1):
        if question.get("id") not in question_ids:
            continue
        records.append({
            "question_index": index,
            "question_id": question.get("id"),
            "question": question.get("question", ""),
            "missing_terms": [],
        })
    return records

def _collect_existing_domain_terms(question, domain_path, top_k=12):
    extractor = GeoKeywordExtractor(
        domain_csv=domain_path,
        synonym_csv="geo_synonyms.csv" if os.path.exists("geo_synonyms.csv") else None,
    )
    options = question.get("options", {}) or {}
    combined_text = "。".join([question.get("question", "")] + [str(value) for value in options.values()])
    keywords = _refine_keywords(extractor.extract_keywords(combined_text, top_k=top_k))

    terms = {}
    for keyword in keywords:
        entry = extractor.domain_entry(keyword)
        if entry:
            terms[keyword] = entry

    for option_text in options.values():
        entry = extractor.domain_entry(option_text)
        if entry:
            terms[str(option_text)] = entry

    return terms

def _parse_llm_answer_label(response, option_labels):
    text = str(response or "").strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            raw = data.get("answer") or data.get("答案") or data.get("label") or data.get("选项")
            if isinstance(raw, list):
                labels = [str(item).strip().upper() for item in raw]
            else:
                labels = [str(raw).strip().upper()]
            labels = [label for label in labels if label in option_labels]
            if labels:
                return sorted(set(labels))
    except json.JSONDecodeError:
        pass

    labels = re.findall(r"\b[A-Z]\b", text.upper())
    labels = [label for label in labels if label in option_labels]
    return sorted(set(labels)) if labels else []

def _build_single_question_dcr_prompt(question, related_terms):
    options = question.get("options", {}) or {}
    term_lines = []
    for term, info in related_terms.items():
        if not info:
            continue
        term_lines.append(
            f"- {term}: 分类={info.get('分类', '')}; 上级={info.get('上级', '')}; 下级={info.get('下级', '')}"
        )

    option_text = "\n".join(f"{label}. {value}" for label, value in options.items())
    term_text = "\n".join(term_lines) if term_lines else "（无）"
    return f"""你是地理选择题判题助手。请只根据题干、选项和补充词典信息判断单选题答案。

题干:
{question.get('question', '')}

选项:
{option_text}

DCR补充词典信息:
{term_text}

要求:
1. 这是单选题，只能选择一个选项。
2. 不要解释，不要输出多余文字。
3. 按JSON回答: {{"answer": "A", "confidence": 0.85}}
"""

def _generate_dcr_answer_overrides(dcr_extractor, questions, missing_records, retrieval_results, domain_path):
    if not dcr_extractor.dcr or not dcr_extractor.dcr.llm_provider:
        return {}

    question_by_id = {q.get("id"): q for q in questions}
    overrides = {}
    for record in missing_records:
        qid = record.get("question_id")
        question = question_by_id.get(qid)
        if not question or str(question.get("type", "")).strip().lower() == "multiple":
            continue

        options = question.get("options", {}) or {}
        option_labels = set(options.keys())
        related_terms = {
            term: retrieval_results.get(term)
            for term in record.get("missing_terms", [])
            if retrieval_results.get(term)
        }
        if not related_terms:
            related_terms = _collect_existing_domain_terms(question, domain_path)
        if not related_terms:
            continue

        prompt = _build_single_question_dcr_prompt(question, related_terms)
        try:
            response = dcr_extractor.dcr.llm_provider.query(prompt, max_tokens=200)
        except Exception as e:
            print(f">>> DCR辅助判题失败 Q{qid}: {e}")
            continue

        answer = _parse_llm_answer_label(response, option_labels)
        if len(answer) == 1:
            overrides[str(qid)] = answer
            print(f">>> DCR辅助判题 Q{qid}: {answer[0]}")

    return overrides

def _index_results_by_question_id(evaluation_result):
    indexed = {}
    for item in (evaluation_result or {}).get("results", []):
        indexed[str(item.get("question_id"))] = item
    return indexed

def _write_dcr_reports(
    report_path,
    summary_path,
    domain_path,
    llm_config,
    dcr_target,
    baseline,
    affected_baseline_count,
    after_result,
    missing_records,
    retrieval_results,
    answer_overrides=None,
    enable_answer_override=False,
):
    baseline_by_id = _index_results_by_question_id(baseline)
    after_by_id = _index_results_by_question_id(after_result)

    comparisons = []
    improved = declined = unchanged = 0
    before_correct = after_correct = 0
    for record in missing_records:
        qid = str(record.get("question_id"))
        before = baseline_by_id.get(qid, {})
        after = after_by_id.get(qid, {})
        before_ok = bool(before.get("is_correct"))
        after_ok = bool(after.get("is_correct"))
        before_correct += int(before_ok)
        after_correct += int(after_ok)
        if before_ok != after_ok:
            if after_ok:
                improved += 1
            else:
                declined += 1
        else:
            unchanged += 1

        comparisons.append({
            "question_id": record.get("question_id"),
            "question_index": record.get("question_index"),
            "missing_terms": record.get("missing_terms", []),
            "before_correct": before_ok,
            "after_correct": after_ok,
            "before_prediction": before.get("predicted_answer"),
            "after_prediction": after.get("predicted_answer"),
            "before_prediction_source": before.get("prediction_source", "symbolic_system"),
            "after_prediction_source": after.get("prediction_source", "symbolic_system"),
            "correct_answer": before.get("correct_answer") or after.get("correct_answer"),
        })

    report = {
        "dictionary": domain_path,
        "llm_provider": llm_config.get("provider"),
        "llm_model": llm_config.get("model"),
        "dcr_target": dcr_target,
        "dcr_answer_override_enabled": enable_answer_override,
        "baseline": {
            "total_count": (baseline or {}).get("total_count", 0),
            "correct_count": (baseline or {}).get("correct_count", 0),
            "accuracy": (baseline or {}).get("accuracy", 0.0),
        },
        "overall_after_dcr": {
            "total_count": (after_result or {}).get("total_count", 0),
            "correct_count": (after_result or {}).get("correct_count", 0),
            "accuracy": (after_result or {}).get("accuracy", 0.0),
        },
        "affected_questions_before": {
            "total_count": affected_baseline_count,
            "correct_count": before_correct,
            "accuracy": before_correct / affected_baseline_count if affected_baseline_count else 0.0,
        },
        "affected_questions_after": {
            "total_count": affected_baseline_count,
            "correct_count": after_correct,
            "accuracy": after_correct / affected_baseline_count if affected_baseline_count else 0.0,
        },
        "delta": {
            "correct_count_delta": after_correct - before_correct,
            "accuracy_delta": (
                (after_correct / affected_baseline_count if affected_baseline_count else 0.0)
                - (before_correct / affected_baseline_count if affected_baseline_count else 0.0)
            ),
            "overall_correct_count_delta": (after_result or {}).get("correct_count", 0) - (baseline or {}).get("correct_count", 0),
            "overall_accuracy_delta": (after_result or {}).get("accuracy", 0.0) - (baseline or {}).get("accuracy", 0.0),
            "improved_questions": improved,
            "declined_questions": declined,
            "unchanged_questions": unchanged,
        },
        "missing_records": missing_records,
        "retrieved_terms": {
            term: info for term, info in retrieval_results.items() if info
        },
        "answer_overrides": answer_overrides or {},
        "failed_terms": [
            term for term, info in retrieval_results.items() if not info
        ],
        "comparisons": comparisons,
    }

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("=== DCR 两阶段评测摘要 ===\n")
        f.write(f"词典: {domain_path}\n")
        f.write(f"LLM: {llm_config.get('provider')} / {llm_config.get('model')}\n")
        f.write(f"DCR扩展范围: {dcr_target}\n")
        f.write(f"DCR辅助判题覆盖: {'启用' if enable_answer_override else '禁用'}\n")
        f.write(f"基线整体准确率: {report['baseline']['accuracy'] * 100:.2f}% ")
        f.write(f"({report['baseline']['correct_count']}/{report['baseline']['total_count']})\n")
        f.write(f"DCR后整体准确率: {report['overall_after_dcr']['accuracy'] * 100:.2f}% ")
        f.write(f"({report['overall_after_dcr']['correct_count']}/{report['overall_after_dcr']['total_count']})\n")
        f.write(f"整体准确率变化: {report['delta']['overall_accuracy_delta'] * 100:+.2f}%\n")
        f.write(f"陌生词相关题目前准确率: {report['affected_questions_before']['accuracy'] * 100:.2f}% ")
        f.write(f"({before_correct}/{affected_baseline_count})\n")
        f.write(f"扩词典后二次准确率: {report['affected_questions_after']['accuracy'] * 100:.2f}% ")
        f.write(f"({after_correct}/{affected_baseline_count})\n")
        f.write(f"准确率变化（只比较陌生词相关题目）: {report['delta']['accuracy_delta'] * 100:+.2f}%\n")
        f.write(f"改善/下降/不变: {improved}/{declined}/{unchanged}\n")
        f.write(f"成功扩展词条数: {len(report['retrieved_terms'])}\n")
        f.write(f"DCR辅助判题覆盖数: {len(report['answer_overrides'])}\n")
        f.write(f"检索失败词条数: {len(report['failed_terms'])}\n")
        if not report["retrieved_terms"] and report["failed_terms"]:
            f.write("提示: 本次没有成功扩展任何词条，二次测试实际仍使用原词典。\n")
        f.write("说明: 基线和DCR后整体准确率使用全题库；扩展前后子集准确率只使用本轮DCR实际覆盖的题目。\n")

def evaluate_json_with_dcr(
    json_path,
    custom_dict=None,
    llm_provider=None,
    model=None,
    api_key=None,
    cache_dir=".dcr_cache",
    dcr_target="wrong",
    enable_answer_override=False,
):
    domain_path = _resolve_domain_path(json_path, custom_dict)
    llm_config = _build_llm_config(llm_provider, model, api_key)
    try:
        _validate_llm_config_for_dcr(llm_config)
    except ValueError as e:
        print(f"DCR配置错误: {e}")
        return None

    print("=" * 70)
    print("【DCR 两阶段批量测试】")
    print(f"题库: {json_path}")
    print(f"词典: {domain_path}")
    print(f"LLM: {llm_config.get('provider')} / {llm_config.get('model')}")
    print("=" * 70)

    print("\n>>> 阶段1：使用原词典进行基线测试")
    baseline = evaluate_json(json_path, custom_dict=domain_path)
    if not baseline:
        print("基线测试失败，终止 DCR 流程。")
        return None

    target_question_ids = None
    if dcr_target == "wrong":
        target_question_ids = {
            item.get("question_id")
            for item in baseline.get("results", [])
            if not item.get("is_correct")
        }
        print(f"\n>>> 阶段2：检测基线答错题中的陌生术语/关键词（{len(target_question_ids)}题）")
    else:
        print("\n>>> 阶段2：检测全部题目中的陌生术语/关键词")

    missing_records, unique_terms, questions, contexts_by_term = _detect_missing_terms_by_question(
        json_path,
        domain_path,
        allowed_question_ids=target_question_ids,
    )
    print(f">>> 涉及陌生词的题目数: {len(missing_records)}")
    print(f">>> 唯一陌生词数: {len(unique_terms)}")

    if not unique_terms:
        print("未检测到需要新增扩展的陌生词，将直接使用当前词典进行二次系统评测。")
        retrieval_results = {}
        missing_records = _build_records_for_question_ids(questions, target_question_ids or [])
        dcr_extractor = create_extractor_with_dcr(
            domain_csv=domain_path,
            synonym_csv="geo_synonyms.csv" if os.path.exists("geo_synonyms.csv") else None,
            llm_config=llm_config,
            cache_dir=cache_dir,
            enable_dcr=True,
            auto_update=False,
        )
    else:
        print("\n>>> 阶段3：调用 DCR 扩展词典")
        dcr_extractor = create_extractor_with_dcr(
            domain_csv=domain_path,
            synonym_csv="geo_synonyms.csv" if os.path.exists("geo_synonyms.csv") else None,
            llm_config=llm_config,
            cache_dir=cache_dir,
            enable_dcr=True,
            auto_update=True,
        )
        retrieval_results = _retrieve_missing_terms_with_context(
            dcr_extractor,
            unique_terms,
            contexts_by_term,
            domain_path,
        )
        dcr_extractor.export_missing_concepts(os.path.join("test_results", "dcr_missing_concepts.json"))
        _clear_keyword_extractor_cache(domain_path)

    answer_overrides = {}
    if enable_answer_override:
        print("\n>>> 阶段3.5：对DCR覆盖的单选错题进行辅助判题（已显式启用，不计入纯系统能力评测）")
        answer_overrides = _generate_dcr_answer_overrides(
            dcr_extractor,
            questions,
            missing_records,
            retrieval_results,
            domain_path,
        )
        print(f">>> DCR辅助判题覆盖题数: {len(answer_overrides)}")
    else:
        print("\n>>> 阶段3.5：跳过DCR辅助判题，二次评测只统计系统自身预测")

    affected_ids = {record["question_id"] for record in missing_records}
    affected_questions = [q for q in questions if q.get("id") in affected_ids]
    _write_geography_questions(os.path.join("test_results", "dcr_affected_questions.json"), affected_questions)

    print("\n>>> 阶段4：使用扩展后的词典重新测试完整题库")
    after_result = evaluate_json(json_path, custom_dict=domain_path, answer_overrides=answer_overrides)

    report_path = os.path.join("test_results", "dcr_evaluation_report.json")
    summary_path = os.path.join("test_results", "dcr_evaluation_summary.txt")
    _write_dcr_reports(
        report_path=report_path,
        summary_path=summary_path,
        domain_path=domain_path,
        llm_config=llm_config,
        dcr_target=dcr_target,
        baseline=baseline,
        affected_baseline_count=len(affected_questions),
        after_result=after_result,
        missing_records=missing_records,
        retrieval_results=retrieval_results,
        answer_overrides=answer_overrides,
        enable_answer_override=enable_answer_override,
    )

    print("\n>>> DCR 两阶段评测完成")
    print(f">>> 详细报告: {report_path}")
    print(f">>> 摘要报告: {summary_path}")
    return after_result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="一键批量测试题库并验证准确率")
    parser.add_argument("json_file", nargs='?', default=None, help="题目JSON文件路径")
    parser.add_argument("-d", "--dict", default=None, help="可选：指定要使用的领域词典文件路径 (例如: single_dictionary/dic1.csv)")
    parser.add_argument("--enable-dcr", action="store_true", help="启用DCR两阶段评测：先测原词典，再扩展词典并重测陌生词相关题目")
    parser.add_argument("--llm-provider", choices=["deepseek", "openai", "anthropic", "local"], default=None, help="DCR调用的大模型提供方；不填时按环境变量自动选择")
    parser.add_argument("--model", default=None, help="DCR调用的模型名称；不填时使用提供方默认模型")
    parser.add_argument("--api-key", default=None, help="可选：直接传入API Key；通常建议用环境变量预设")
    parser.add_argument("--cache-dir", default=".dcr_cache", help="DCR缓存目录")
    parser.add_argument("--dcr-target", choices=["wrong", "all"], default="wrong", help="DCR扩展范围：wrong=只扩展基线答错题；all=扩展全部检测到陌生词的题目")
    parser.add_argument(
        "--enable-dcr-answer-override",
        action="store_true",
        help="显式启用旧版DCR辅助判题覆盖。默认关闭；关闭时DCR只扩展词典，准确率只统计系统自身预测。",
    )
    args = parser.parse_args()

    if args.json_file and os.path.exists(args.json_file):
        if args.enable_dcr:
            evaluate_json_with_dcr(
                args.json_file,
                custom_dict=args.dict,
                llm_provider=args.llm_provider,
                model=args.model,
                api_key=args.api_key,
                cache_dir=args.cache_dir,
                dcr_target=args.dcr_target,
                enable_answer_override=args.enable_dcr_answer_override,
            )
        else:
            evaluate_json(args.json_file, custom_dict=args.dict)
    else:
        print("请提供有效的 JSON 文件路径。")
        print("示例语法：python batch_evaluate.py single_questions/Climatology.json -d dict_single/Climatology.csv")
        print("启用DCR：python batch_evaluate.py single_questions/Climatology.json -d dict_single/Climatology.csv --enable-dcr --llm-provider deepseek")
