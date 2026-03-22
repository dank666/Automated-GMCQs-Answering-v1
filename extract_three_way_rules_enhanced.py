#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
改进的三支概念规则提取算法
基于多维度评估的智能规则生成策略
"""

import re
import os
import pandas as pd
import numpy as np
from collections import defaultdict
import math

def parse_three_way_concept(line):
    """解析三支概念字符串 ((X),(Y))#((A),(B))"""
    pattern = r'\(\(([^)]*)\),\s*\(([^)]*)\)\)#\(\(([^)]*)\),\s*\(([^)]*)\)\)'
    match = re.match(pattern, line.strip())
    
    if match:
        x_str, y_str, a_str, b_str = match.groups()
        
        def parse_set(s):
            if not s.strip():
                return set()
            return set(map(int, s.split(', ')))
        
        X = parse_set(x_str)
        Y = parse_set(y_str)  
        A = parse_set(a_str)
        B = parse_set(b_str)
        
        return X, Y, A, B
    else:
        return None

def load_three_way_concepts(file_path):
    """从文件中加载三支概念"""
    condition_concepts = []
    decision_concepts = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    current_section = None
    
    for line in lines:
        line = line.strip()
        
        if "OAELGMI" in line and "条件属性" in line:
            current_section = "condition"
            continue
        elif "OAELGNJ" in line and "决策属性" in line:
            current_section = "decision"
            continue
        elif line.startswith("统计信息") or line.startswith("==="):
            current_section = None
            continue
        
        if current_section and line and not line.startswith("-") and ". " in line:
            concept_str = line.split(". ", 1)[1] if ". " in line else line
            parsed = parse_three_way_concept(concept_str)
            
            if parsed:
                X, Y, A, B = parsed
                concept_dict = {'X': X, 'Y': Y, 'A': A, 'B': B}
                
                if current_section == "condition":
                    condition_concepts.append(concept_dict)
                elif current_section == "decision":
                    decision_concepts.append(concept_dict)
    
    return condition_concepts, decision_concepts

def calculate_concept_strength(concept):
    """计算概念强度：基于对象覆盖度和属性特异性"""
    X, Y, A, B = concept['X'], concept['Y'], concept['A'], concept['B']
    
    # 对象覆盖度：正域对象数 / (正域 + 负域)
    object_coverage = len(X) / (len(X) + len(Y) + 1)  # +1避免除零
    
    # 属性特异性：较小的属性集更具特异性
    attr_specificity = 1 / (len(A) + len(B) + 1)  # +1避免除零
    
    # 概念紧密度：非空集合的比例
    compactness = sum([bool(X), bool(Y), bool(A), bool(B)]) / 4
    
    return object_coverage * attr_specificity * compactness

def calculate_semantic_similarity(concept1, concept2):
    """计算两个概念的语义相似度"""
    X1, Y1, A1, B1 = concept1['X'], concept1['Y'], concept1['A'], concept1['B']
    X2, Y2, A2, B2 = concept2['X'], concept2['Y'], concept2['A'], concept2['B']
    
    # Jaccard相似度
    def jaccard_similarity(set1, set2):
        if not set1 and not set2:
            return 1.0
        union = set1.union(set2)
        if not union:
            return 0.0
        intersection = set1.intersection(set2)
        return len(intersection) / len(union)
    
    # 计算各部分相似度
    x_sim = jaccard_similarity(X1, X2)
    y_sim = jaccard_similarity(Y1, Y2)
    a_sim = jaccard_similarity(A1, A2)
    b_sim = jaccard_similarity(B1, B2)
    
    # 加权平均（对象域权重更高）
    return (x_sim * 0.3 + y_sim * 0.3 + a_sim * 0.2 + b_sim * 0.2)

def enhanced_rule_generation(condition_concepts, decision_concepts, min_strength=0.1, min_similarity=0.1):
    """
    改进的规则生成算法
    考虑概念强度、语义相似度和包含关系的多维度评估
    """
    print(f"条件概念数量: {len(condition_concepts)}")
    print(f"决策概念数量: {len(decision_concepts)}")
    
    # 预计算概念强度
    cond_strengths = [calculate_concept_strength(c) for c in condition_concepts]
    dec_strengths = [calculate_concept_strength(c) for c in decision_concepts]
    
    print(f"条件概念平均强度: {sum(cond_strengths)/len(cond_strengths):.3f}")
    print(f"决策概念平均强度: {sum(dec_strengths)/len(dec_strengths):.3f}")
    
    candidate_rules = []
    
    for i, cond_concept in enumerate(condition_concepts):
        X, Y, A, B = cond_concept['X'], cond_concept['Y'], cond_concept['A'], cond_concept['B']
        cond_strength = cond_strengths[i]
        
        # 跳过弱概念
        if cond_strength < min_strength:
            continue
            
        for j, dec_concept in enumerate(decision_concepts):
            Z, W, C, D = dec_concept['X'], dec_concept['Y'], dec_concept['A'], dec_concept['B']
            dec_strength = dec_strengths[j]
            
            # 跳过弱概念
            if dec_strength < min_strength:
                continue
            
            # 计算语义相似度
            similarity = calculate_semantic_similarity(cond_concept, dec_concept)
            
            # 检查包含关系和相似度
            inclusion_score = 0
            if X.issubset(Z) and Y.issubset(W):
                inclusion_score = 1.0
            elif X.intersection(Z) or Y.intersection(W):
                # 部分包含也给予一定分数
                x_overlap = len(X.intersection(Z)) / max(len(X), 1)
                y_overlap = len(Y.intersection(W)) / max(len(Y), 1)
                inclusion_score = (x_overlap + y_overlap) / 2
            
            # 综合评分
            rule_score = (inclusion_score * 0.4 + similarity * 0.3 + 
                         cond_strength * 0.15 + dec_strength * 0.15)
            
            # 生成规则 A→C
            if A and C and rule_score > min_similarity:
                candidate_rules.append({
                    'premise': A.copy(),
                    'conclusion': C.copy(),
                    'type': 'A→C',
                    'score': rule_score,
                    'inclusion_score': inclusion_score,
                    'similarity': similarity,
                    'cond_strength': cond_strength,
                    'dec_strength': dec_strength,
                    'condition_concept_id': i,
                    'decision_concept_id': j,
                })
            
            # 生成规则 B→D  
            if B and D and rule_score > min_similarity:
                candidate_rules.append({
                    'premise': B.copy(),
                    'conclusion': D.copy(),
                    'type': 'B→D',
                    'score': rule_score,
                    'inclusion_score': inclusion_score,
                    'similarity': similarity,
                    'cond_strength': cond_strength,
                    'dec_strength': dec_strength,
                    'condition_concept_id': i,
                    'decision_concept_id': j,
                })
    
    # 按评分排序
    candidate_rules.sort(key=lambda x: x['score'], reverse=True)
    
    print(f"候选规则数量: {len(candidate_rules)}")
    if candidate_rules:
        print(f"最高评分: {candidate_rules[0]['score']:.3f}")
        print(f"最低评分: {candidate_rules[-1]['score']:.3f}")
    
    return candidate_rules

def intelligent_redundancy_removal(rules, similarity_threshold=0.8):
    """
    智能冗余消除：基于规则相似度和评分的分层过滤
    """
    if not rules:
        return []
    
    print(f"冗余消除前规则数量: {len(rules)}")
    
    # 第一层：移除完全相同的规则
    unique_rules = []
    seen_rules = set()
    
    for rule in rules:
        rule_signature = (frozenset(rule['premise']), frozenset(rule['conclusion']), rule['type'])
        if rule_signature not in seen_rules:
            seen_rules.add(rule_signature)
            unique_rules.append(rule)
    
    print(f"去除重复规则后: {len(unique_rules)} 个规则")
    
    # 第二层：基于包含关系的冗余消除
    non_redundant_rules = []
    
    for i, rule1 in enumerate(unique_rules):
        is_redundant = False
        
        for j, rule2 in enumerate(unique_rules):
            if i != j and rule1['type'] == rule2['type']:
                # 如果rule1的结论是rule2结论的子集（rule1更弱），且前提相同或相近，则rule1冗余
                if (rule1['premise'] == rule2['premise'] and 
                    rule1['conclusion'].issubset(rule2['conclusion']) and
                    rule1['conclusion'] != rule2['conclusion'] and
                    rule2['score'] >= rule1['score'] * 0.8):  # rule2评分不能太低
                    is_redundant = True
                    break
        
        if not is_redundant:
            non_redundant_rules.append(rule1)
    
    print(f"去除包含冗余后: {len(non_redundant_rules)} 个规则")
    
    # 第三层：基于语义相似度的聚类去重
    final_rules = []
    processed = set()
    
    for i, rule1 in enumerate(non_redundant_rules):
        if i in processed:
            continue
            
        cluster = [rule1]
        processed.add(i)
        
        for j, rule2 in enumerate(non_redundant_rules):
            if j in processed or i == j:
                continue
                
            # 计算规则语义相似度
            premise_sim = len(rule1['premise'].intersection(rule2['premise'])) / len(rule1['premise'].union(rule2['premise']))
            conclusion_sim = len(rule1['conclusion'].intersection(rule2['conclusion'])) / len(rule1['conclusion'].union(rule2['conclusion']))
            
            if premise_sim > similarity_threshold and conclusion_sim > similarity_threshold:
                cluster.append(rule2)
                processed.add(j)
        
        # 从每个聚类中选择最佳规则
        best_rule = max(cluster, key=lambda x: x['score'])
        final_rules.append(best_rule)
    
    print(f"智能去重后最终规则数量: {len(final_rules)}")
    return final_rules

def enhanced_confidence_calculation(rules, df, objects, all_attrs):
    """改进的置信度和支持度计算"""
    if df is None:
        return rules
    
    total_objects = len(objects)
    attr_columns = all_attrs
    data_matrix = df.iloc[:, 1:].to_numpy(dtype=int, copy=False)
    
    # 创建属性映射
    attr_id_to_col = {}
    for i, col in enumerate(attr_columns):
        attr_id_to_col[i + 1] = col
    col_name_to_idx = {col: idx for idx, col in enumerate(attr_columns)}
    
    enriched_rules = []
    
    for rule in rules:
        premise = rule['premise']
        conclusion = rule['conclusion']
        premise_col_indices = [
            col_name_to_idx[attr_id_to_col[attr_id]]
            for attr_id in premise
            if attr_id in attr_id_to_col and attr_id_to_col[attr_id] in col_name_to_idx
        ]
        conclusion_col_indices = [
            col_name_to_idx[attr_id_to_col[attr_id]]
            for attr_id in conclusion
            if attr_id in attr_id_to_col and attr_id_to_col[attr_id] in col_name_to_idx
        ]
        
        premise_weights = {}
        if premise_col_indices:
            premise_slice = data_matrix[:, premise_col_indices]
            weight_ratios = premise_slice.mean(axis=1)
            premise_mask = weight_ratios >= 0.6
            premise_indices = np.flatnonzero(premise_mask)
            premise_objects = set(premise_indices.tolist())
            premise_weights = {idx: float(weight_ratios[idx]) for idx in premise_indices}
        else:
            weight_ratios = np.zeros(total_objects, dtype=float)
            premise_mask = np.zeros(total_objects, dtype=bool)
            premise_objects = set()
        
        if conclusion_col_indices:
            conclusion_slice = data_matrix[:, conclusion_col_indices]
            conclusion_mask = np.all(conclusion_slice == 1, axis=1)
        else:
            conclusion_mask = np.ones(total_objects, dtype=bool)
        conclusion_indices = np.flatnonzero(conclusion_mask)
        conclusion_objects = set(conclusion_indices.tolist())
        
        intersection_mask = premise_mask & conclusion_mask
        intersection_indices = np.flatnonzero(intersection_mask)
        intersection = set(intersection_indices.tolist())
        weighted_intersection = float(weight_ratios[intersection_mask].sum()) if premise_col_indices else 0.0
        
        # 改进的置信度计算
        if len(premise_objects) > 0:
            # 传统置信度
            traditional_confidence = len(intersection) / len(premise_objects)
            # 加权置信度
            weighted_confidence = weighted_intersection / len(premise_objects)
            # 最终置信度（取两者平均）
            confidence = (traditional_confidence + weighted_confidence) / 2
        else:
            confidence = 0
        
        # 支持度
        support = len(intersection) / total_objects
        
        # 提升度 (Lift)
        conclusion_prob = len(conclusion_objects) / total_objects
        lift = confidence / conclusion_prob if conclusion_prob > 0 else 0
        
        # 规则强度综合评分
        rule_strength = rule['score'] * 0.4 + confidence * 0.3 + support * 0.2 + min(lift, 2) * 0.1
        
        rule['confidence'] = confidence
        rule['support'] = support
        rule['lift'] = lift
        rule['rule_strength'] = rule_strength
        rule['premise_objects'] = premise_objects
        rule['conclusion_objects'] = conclusion_objects
        rule['intersection'] = intersection
        rule['weighted_intersection'] = weighted_intersection
        
        # Add actual attribute names
        rule['premise_names'] = [attr_id_to_col[attr_id] for attr_id in premise if attr_id in attr_id_to_col]
        rule['conclusion_names'] = [attr_id_to_col[attr_id] for attr_id in conclusion if attr_id in attr_id_to_col]
        
        enriched_rules.append(rule)
    
    return enriched_rules

def adaptive_threshold_selection(rules):
    """自适应阈值选择"""
    if not rules:
        return 0.5, 0.1, 0.3
    
    confidences = [r['confidence'] for r in rules if r['confidence'] > 0]
    supports = [r['support'] for r in rules if r['support'] > 0]
    rule_strengths = [r['rule_strength'] for r in rules]
    
    if not confidences or not supports:
        return 0.3, 0.05, 0.2  # 更宽松的默认阈值
    
    # 使用四分位数方法确定阈值
    confidences.sort()
    supports.sort()
    rule_strengths.sort()
    
    # 取第75百分位作为高质量阈值
    q75_conf = confidences[int(len(confidences) * 0.75)]
    q75_supp = supports[int(len(supports) * 0.75)]
    q75_strength = rule_strengths[int(len(rule_strengths) * 0.75)]
    
    # 取第50百分位作为中等质量阈值
    q50_conf = confidences[int(len(confidences) * 0.5)]
    q50_supp = supports[int(len(supports) * 0.5)]
    
    # 动态选择阈值
    min_confidence = max(0.3, min(0.8, q50_conf * 0.8))
    min_support = max(0.05, min(0.3, q50_supp * 0.8))
    min_strength = max(0.2, q75_strength * 0.7)
    
    print(f"自适应阈值：置信度≥{min_confidence:.3f}, 支持度≥{min_support:.3f}, 强度≥{min_strength:.3f}")
    
    return min_confidence, min_support, min_strength

def filter_high_quality_rules(rules):
    """基于多指标的高质量规则筛选"""
    if not rules:
        return []
    
    min_confidence, min_support, min_strength = adaptive_threshold_selection(rules)
    
    high_quality_rules = []
    for rule in rules:
        if (rule['confidence'] >= min_confidence and 
            rule['support'] >= min_support and 
            rule['rule_strength'] >= min_strength):
            high_quality_rules.append(rule)
    
    # 如果高质量规则太少，降低阈值
    if len(high_quality_rules) < 3:
        print("高质量规则数量不足，降低阈值...")
        min_confidence *= 0.7
        min_support *= 0.7
        min_strength *= 0.7
        
        high_quality_rules = []
        for rule in rules:
            if (rule['confidence'] >= min_confidence and 
                rule['support'] >= min_support and 
                rule['rule_strength'] >= min_strength):
                high_quality_rules.append(rule)
    
    # 按综合强度排序
    high_quality_rules.sort(key=lambda x: x['rule_strength'], reverse=True)
    
    return high_quality_rules

def load_decision_context_data(csv_file_path):
    """加载决策形式背景数据"""
    try:
        df = pd.read_csv(csv_file_path, encoding='utf-8')
        objects = df.iloc[:, 0].tolist()
        all_attrs = df.columns[1:].tolist()
        
        print(f"对象数量: {len(objects)}")
        print(f"属性数量: {len(all_attrs)}")
        
        return objects, all_attrs, df
        
    except Exception as e:
        print(f"读取CSV文件失败: {e}")
        return None, None, None

def save_enhanced_results(rules, filename_prefix="enhanced"):
    """保存改进算法的结果"""
    os.makedirs("test_results", exist_ok=True)
    
    with open(f"test_results/{filename_prefix}_rules_analysis.txt", 'w', encoding='utf-8') as f:
        f.write("改进的三支概念规则提取结果分析\n")
        f.write("=" * 60 + "\n\n")
        
        f.write("算法改进要点：\n")
        f.write("1. 多维度概念强度评估\n")
        f.write("2. 语义相似度计算\n")
        f.write("3. 智能冗余消除策略\n")
        f.write("4. 加权置信度计算\n")
        f.write("5. 自适应阈值选择\n\n")
        
        f.write(f"提取的高质量规则数量: {len(rules)}\n\n")
        
        for i, rule in enumerate(rules, 1):
            f.write(f"{i}. {{{', '.join(map(str, sorted(rule['premise'])))}}} → {{{', '.join(map(str, sorted(rule['conclusion'])))}}}\n")
            f.write(f"   类型: {rule['type']}\n")
            f.write(f"   综合评分: {rule['score']:.3f}\n")
            f.write(f"   置信度: {rule['confidence']:.3f}\n")
            f.write(f"   支持度: {rule['support']:.3f}\n")
            f.write(f"   提升度: {rule['lift']:.3f}\n")
            f.write(f"   规则强度: {rule['rule_strength']:.3f}\n")
            f.write(f"   包含评分: {rule['inclusion_score']:.3f}\n")
            f.write(f"   语义相似度: {rule['similarity']:.3f}\n")
            f.write(f"   前提对象数: {len(rule['premise_objects'])}\n")
            f.write(f"   结论对象数: {len(rule['conclusion_objects'])}\n")
            f.write(f"   交集对象数: {len(rule['intersection'])}\n")
            f.write(f"   加权交集: {rule['weighted_intersection']:.2f}\n")
            f.write("\n")

def main():
    """主函数"""
    print("=== 改进的三支概念规则提取算法 ===")
    
    # 文件路径
    concepts_file = "test_results/merged_three_way_concepts.txt"
    decision_context_file = "test_contexts/decision_formal_context.csv"
    
    if not os.path.exists(concepts_file):
        print(f"错误：找不到文件 {concepts_file}")
        return
    
    # 加载三支概念
    print("\n步骤1：加载三支概念...")
    condition_concepts, decision_concepts = load_three_way_concepts(concepts_file)
    print(f"条件概念: {len(condition_concepts)} 个")
    print(f"决策概念: {len(decision_concepts)} 个")
    
    # 改进的规则生成
    print("\n步骤2：智能规则生成...")
    candidate_rules = enhanced_rule_generation(condition_concepts, decision_concepts, 
                                              min_strength=0.001, min_similarity=0.05)
    
    # 智能冗余消除
    print("\n步骤3：智能冗余消除...")
    non_redundant_rules = intelligent_redundancy_removal(candidate_rules, similarity_threshold=0.7)
    
    # 加载决策背景数据
    print("\n步骤4：加载决策背景数据...")
    objects, all_attrs, df = load_decision_context_data(decision_context_file)
    
    if objects is not None:
        # 改进的置信度计算
        print("\n步骤5：计算改进的置信度和支持度...")
        enriched_rules = enhanced_confidence_calculation(non_redundant_rules, df, objects, all_attrs)
        
        # 高质量规则筛选
        print("\n步骤6：筛选高质量规则...")
        final_rules = filter_high_quality_rules(enriched_rules)
        
        # 保存结果
        print("\n步骤7：保存结果...")
        save_enhanced_results(final_rules)
        
        print(f"\n=== 算法执行完成 ===")
        print(f"最终提取的高质量规则数量: {len(final_rules)}")
        if final_rules:
            avg_confidence = sum(r['confidence'] for r in final_rules) / len(final_rules)
            avg_support = sum(r['support'] for r in final_rules) / len(final_rules)
            avg_strength = sum(r['rule_strength'] for r in final_rules) / len(final_rules)
            print(f"平均置信度: {avg_confidence:.3f}")
            print(f"平均支持度: {avg_support:.3f}")
            print(f"平均规则强度: {avg_strength:.3f}")
            
        return final_rules
    else:
        print("无法加载决策背景数据，跳过置信度计算")
        return []

if __name__ == "__main__":
    main()
