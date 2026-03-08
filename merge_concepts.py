import re

def parse_oe_concept(line):
    """解析OE概念: (X)#((A),(B))"""
    # 匹配格式: (X)#((A),(B))
    pattern = r'\(([^)]*)\)#\(\(([^)]*)\),\s*\(([^)]*)\)\)'
    match = re.match(pattern, line.strip())
    
    if match:
        x_str, a_str, b_str = match.groups()
        
        def parse_set(s):
            if not s.strip():
                return set()
            elements = [elem.strip() for elem in s.split(',') if elem.strip()]
            return set(map(int, elements))
        
        X = parse_set(x_str)
        A = parse_set(a_str)
        B = parse_set(b_str)
        
        return X, A, B
    return None, None, None

def parse_ae_concept(line):
    """解析AE概念: ((X),(Y))#(A)"""
    # 匹配格式: ((X),(Y))#(A)
    pattern = r'\(\(([^)]*)\),\s*\(([^)]*)\)\)#\(([^)]*)\)'
    match = re.match(pattern, line.strip())
    
    if match:
        x_str, y_str, a_str = match.groups()
        
        def parse_set(s):
            if not s.strip():
                return set()
            elements = [elem.strip() for elem in s.split(',') if elem.strip()]
            return set(map(int, elements))
        
        X = parse_set(x_str)
        Y = parse_set(y_str)
        A = parse_set(a_str)
        
        return X, Y, A
    return None, None, None

def load_concepts(file_path):
    """加载OE和AE概念"""
    oe_concepts = []
    ae_concepts = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 找到OE和AE部分的开始位置
    oe_start = None
    ae_start = None
    
    for i, line in enumerate(lines):
        if line.strip() == "OE:":
            oe_start = i + 1
        elif line.strip() == "AE:":
            ae_start = i + 1
            break
    
    if oe_start is None or ae_start is None:
        print(f"错误：在文件 {file_path} 中找不到OE或AE标记")
        return oe_concepts, ae_concepts
    
    # 解析OE概念
    for i in range(oe_start, ae_start - 1):
        if i < len(lines):
            line = lines[i].strip()
            if line and not line.startswith('AE'):
                X, A, B = parse_oe_concept(line)
                if X is not None:
                    oe_concepts.append({'X': X, 'A': A, 'B': B, 'original': line})
    
    # 解析AE概念
    for i in range(ae_start, len(lines)):
        line = lines[i].strip()
        if line:
            X, Y, A = parse_ae_concept(line)
            if X is not None:
                ae_concepts.append({'X': X, 'Y': Y, 'A': A, 'original': line})
    
    return oe_concepts, ae_concepts

def merge_concepts(oe_concepts, ae_concepts):
    """合并AE和OE概念生成三支合并概念"""
    merged_concepts = []
    
    print(f"开始合并概念...")
    print(f"AE概念数量: {len(ae_concepts)}")
    print(f"OE概念数量: {len(oe_concepts)}")
    
    for ae in ae_concepts:
        X_ae, Y_ae, A_ae = ae['X'], ae['Y'], ae['A']
        
        # 查找匹配的OE概念
        matched_oe = None
        
        for oe in oe_concepts:
            X_oe, A_oe, B_oe = oe['X'], oe['A'], oe['B']
            
            # 检查匹配条件：
            # 1. AE的X与OE的X匹配，且AE的A与OE的A匹配
            # 2. 或者AE的Y与OE的X匹配，且AE的A与OE的B匹配
            if (X_ae == X_oe and A_ae == A_oe) or (Y_ae == X_oe and A_ae == B_oe):
                matched_oe = oe
                break
        
        if matched_oe:
            # 生成合并的三支概念: ((X),(Y))#((A),(B))
            X_merged = X_ae
            Y_merged = Y_ae
            
            if X_ae == matched_oe['X'] and A_ae == matched_oe['A']:
                # 情况1: X匹配，A匹配
                A_merged = matched_oe['A']
                B_merged = matched_oe['B']
            else:
                # 情况2: Y匹配，A与B匹配
                A_merged = matched_oe['B']
                B_merged = matched_oe['A']
            
            merged_concepts.append({
                'X': X_merged,
                'Y': Y_merged,
                'A': A_merged,
                'B': B_merged,
                'ae_source': ae['original'],
                'oe_source': matched_oe['original']
            })
    
    print(f"成功合并概念数量: {len(merged_concepts)}")
    return merged_concepts

def format_merged_concept(concept):
    """格式化合并后的三支概念"""
    def format_set(s):
        if not s:
            return ""
        return ", ".join(map(str, sorted(s)))
    
    X = format_set(concept['X'])
    Y = format_set(concept['Y'])
    A = format_set(concept['A'])
    B = format_set(concept['B'])
    
    return f"(({X}), ({Y}))#(({A}), ({B}))"

def main():
    print("="*60)
    print("三支概念合并程序")
    print("="*60)
    
    # 处理条件属性文件
    print("\n处理条件属性文件: threeWcl_condition.txt")
    condition_oe, condition_ae = load_concepts('test_results/threeWcl_condition.txt')
    condition_merged = merge_concepts(condition_oe, condition_ae)
    
    # 处理决策属性文件
    print("\n处理决策属性文件: threeWcl_decision_processed.txt")
    decision_oe, decision_ae = load_concepts('test_results/threeWcl_decision_processed.txt')
    decision_merged = merge_concepts(decision_oe, decision_ae)
    
    # 保存结果
    with open('test_results/merged_three_way_concepts.txt', 'w', encoding='utf-8') as f:
        f.write("三支概念合并结果\n")
        f.write("="*60 + "\n\n")
        
        f.write(f"OAELGMI (条件属性三支合并概念) - 共{len(condition_merged)}个:\n")
        f.write("-"*40 + "\n")
        for i, concept in enumerate(condition_merged, 1):
            f.write(f"{i}. {format_merged_concept(concept)}\n")

        f.write(f"\nOAELGNJ (决策属性三支合并概念) - 共{len(decision_merged)}个:\n")
        f.write("-"*40 + "\n")
        for i, concept in enumerate(decision_merged, 1):
            f.write(f"{i}. {format_merged_concept(concept)}\n")
        
    
    # 分别保存条件和决策概念到独立文件
    with open('test_results/OAELGMI_condition_concepts.txt', 'w', encoding='utf-8') as f:
        f.write("OAELGMI - 条件属性三支合并概念\n")
        f.write("="*40 + "\n")
        for concept in condition_merged:
            f.write(f"{format_merged_concept(concept)}\n")
    
    with open('test_results/OAELGNJ_decision_concepts.txt', 'w', encoding='utf-8') as f:
        f.write("OAELGNJ - 决策属性三支合并概念\n")
        f.write("="*40 + "\n")
        for concept in decision_merged:
            f.write(f"{format_merged_concept(concept)}\n")
    
    print(f"\n处理完成!")
    print(f"合并结果已保存到:")
    print(f"- 综合文件: test_results/merged_three_way_concepts.txt")
    print(f"- 条件概念: test_results/OAELGMI_condition_concepts.txt")
    print(f"- 决策概念: test_results/OAELGNJ_decision_concepts.txt")
    
    print(f"\n统计摘要:")
    print(f"- OAELGMI (条件): {len(condition_merged)}个三支合并概念")
    print(f"- OAELGNJ (决策): {len(decision_merged)}个三支合并概念")

if __name__ == "__main__":
    main()