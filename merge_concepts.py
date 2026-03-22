import re

OE_PATTERN = re.compile(r'\(([^)]*)\)#\(\(([^)]*)\),\s*\(([^)]*)\)\)')
AE_PATTERN = re.compile(r'\(\(([^)]*)\),\s*\(([^)]*)\)\)#\(([^)]*)\)')


def _parse_int_tuple(raw_text):
    cleaned = raw_text.strip()
    if not cleaned:
        return tuple()

    values = [int(part.strip()) for part in cleaned.split(',') if part.strip()]
    return tuple(sorted(values))


def parse_oe_concept(line):
    """解析OE概念: (X)#((A),(B))"""
    match = OE_PATTERN.match(line.strip())
    if not match:
        return None

    x_str, a_str, b_str = match.groups()
    return _parse_int_tuple(x_str), _parse_int_tuple(a_str), _parse_int_tuple(b_str)


def parse_ae_concept(line):
    """解析AE概念: ((X),(Y))#(A)"""
    match = AE_PATTERN.match(line.strip())
    if not match:
        return None

    x_str, y_str, a_str = match.groups()
    return _parse_int_tuple(x_str), _parse_int_tuple(y_str), _parse_int_tuple(a_str)


def load_concepts(file_path):
    """流式加载OE和AE概念，避免全文件读入内存。"""
    oe_concepts = []
    ae_concepts = []
    current_section = None

    with open(file_path, 'r', encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('用时') or line.startswith('len('):
                continue

            if line == "OE:":
                current_section = "oe"
                continue
            if line == "AE:":
                current_section = "ae"
                continue

            if current_section == "oe":
                parsed = parse_oe_concept(line)
                if parsed is None:
                    continue
                x_val, a_val, b_val = parsed
                oe_concepts.append({
                    "X": x_val,
                    "A": a_val,
                    "B": b_val,
                    "original": line,
                })
            elif current_section == "ae":
                parsed = parse_ae_concept(line)
                if parsed is None:
                    continue
                x_val, y_val, a_val = parsed
                ae_concepts.append({
                    "X": x_val,
                    "Y": y_val,
                    "A": a_val,
                    "original": line,
                })

    return oe_concepts, ae_concepts


def _build_oe_index(oe_concepts):
    """
    为OE概念建立两个索引：
    1. (X, A) -> 最早出现的OE
    2. (X, B) -> 最早出现的OE

    保留原始顺序信息，确保在存在多个候选时仍与原先“从前往后扫描OE”的行为一致。
    """
    index_by_x_a = {}
    index_by_x_b = {}

    for position, oe in enumerate(oe_concepts):
        index_by_x_a.setdefault((oe["X"], oe["A"]), (position, oe))
        index_by_x_b.setdefault((oe["X"], oe["B"]), (position, oe))

    return index_by_x_a, index_by_x_b


def merge_concepts(oe_concepts, ae_concepts):
    """基于索引合并AE和OE概念，将复杂度从O(AE*OE)降到O(AE+OE)。"""
    merged_concepts = []

    print("开始合并概念...")
    print(f"AE概念数量: {len(ae_concepts)}")
    print(f"OE概念数量: {len(oe_concepts)}")

    index_by_x_a, index_by_x_b = _build_oe_index(oe_concepts)

    for ae in ae_concepts:
        x_ae = ae["X"]
        y_ae = ae["Y"]
        a_ae = ae["A"]

        candidate_a = index_by_x_a.get((x_ae, a_ae))
        candidate_b = index_by_x_b.get((y_ae, a_ae))

        matched_case = None
        matched_oe = None

        if candidate_a and candidate_b:
            if candidate_a[0] <= candidate_b[0]:
                matched_case = 1
                matched_oe = candidate_a[1]
            else:
                matched_case = 2
                matched_oe = candidate_b[1]
        elif candidate_a:
            matched_case = 1
            matched_oe = candidate_a[1]
        elif candidate_b:
            matched_case = 2
            matched_oe = candidate_b[1]

        if matched_oe is None:
            continue

        if matched_case == 1:
            a_merged = matched_oe["A"]
            b_merged = matched_oe["B"]
        else:
            a_merged = matched_oe["B"]
            b_merged = matched_oe["A"]

        merged_concepts.append({
            "X": x_ae,
            "Y": y_ae,
            "A": a_merged,
            "B": b_merged,
            "ae_source": ae["original"],
            "oe_source": matched_oe["original"],
        })

    print(f"成功合并概念数量: {len(merged_concepts)}")
    return merged_concepts


def format_merged_concept(concept):
    """格式化合并后的三支概念。"""
    def format_set(values):
        return ", ".join(map(str, values))

    x_text = format_set(concept["X"])
    y_text = format_set(concept["Y"])
    a_text = format_set(concept["A"])
    b_text = format_set(concept["B"])
    return f"(({x_text}), ({y_text}))#(({a_text}), ({b_text}))"


def _format_concepts(concepts):
    return [format_merged_concept(concept) for concept in concepts]


def main():
    print("=" * 60)
    print("三支概念合并程序")
    print("=" * 60)

    print("\n处理条件属性文件: threeWcl_condition.txt")
    condition_oe, condition_ae = load_concepts('test_results/threeWcl_condition.txt')
    condition_merged = merge_concepts(condition_oe, condition_ae)

    print("\n处理决策属性文件: threeWcl_decision_processed.txt")
    decision_oe, decision_ae = load_concepts('test_results/threeWcl_decision_processed.txt')
    decision_merged = merge_concepts(decision_oe, decision_ae)

    condition_lines = _format_concepts(condition_merged)
    decision_lines = _format_concepts(decision_merged)

    with open('test_results/merged_three_way_concepts.txt', 'w', encoding='utf-8') as f:
        f.write("三支概念合并结果\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"OAELGMI (条件属性三支合并概念) - 共{len(condition_merged)}个:\n")
        f.write("-" * 40 + "\n")
        for index, line in enumerate(condition_lines, 1):
            f.write(f"{index}. {line}\n")

        f.write(f"\nOAELGNJ (决策属性三支合并概念) - 共{len(decision_merged)}个:\n")
        f.write("-" * 40 + "\n")
        for index, line in enumerate(decision_lines, 1):
            f.write(f"{index}. {line}\n")

    with open('test_results/OAELGMI_condition_concepts.txt', 'w', encoding='utf-8') as f:
        f.write("OAELGMI - 条件属性三支合并概念\n")
        f.write("=" * 40 + "\n")
        for line in condition_lines:
            f.write(f"{line}\n")

    with open('test_results/OAELGNJ_decision_concepts.txt', 'w', encoding='utf-8') as f:
        f.write("OAELGNJ - 决策属性三支合并概念\n")
        f.write("=" * 40 + "\n")
        for line in decision_lines:
            f.write(f"{line}\n")

    print("\n处理完成!")
    print("合并结果已保存到:")
    print("- 综合文件: test_results/merged_three_way_concepts.txt")
    print("- 条件概念: test_results/OAELGMI_condition_concepts.txt")
    print("- 决策概念: test_results/OAELGNJ_decision_concepts.txt")

    print("\n统计摘要:")
    print(f"- OAELGMI (条件): {len(condition_merged)}个三支合并概念")
    print(f"- OAELGNJ (决策): {len(decision_merged)}个三支合并概念")


if __name__ == "__main__":
    main()
