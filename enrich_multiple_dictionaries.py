import json
import os
import re

import pandas as pd


CATEGORY_FILES = {
    "Climatology": "Climatology.csv",
    "Geographical Processes and Principles": "GPP.csv",
    "Human and Economic Geography": "HEG.csv",
    "Hydrology": "Hydrology.csv",
    "Soil and Vegetation": "SV.csv",
    "Topography and Geomorphology": "TG.csv",
}

DEFAULT_FRAGMENT_CATEGORIES = {
    "Climatology": "气象与气候",
    "Geographical Processes and Principles": "地理过程与原理",
    "Human and Economic Geography": "人文与经济地理",
    "Hydrology": "水文地理",
    "Soil and Vegetation": "土壤与植被",
    "Topography and Geomorphology": "地形与地貌",
}

FRAGMENT_BLACKLIST = {
    "正确", "错误", "主要", "典型", "特征", "表现", "说法", "影响",
    "形成", "分布", "原因", "属于", "包括", "体现", "相关", "下列"
}


def normalize_text(text):
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(text or ""))


def merge_delimited_values(current, incoming):
    values = []
    seen = set()
    for raw in (current, incoming):
        if not raw or str(raw).strip() == "nan":
            continue
        for item in str(raw).replace("；", "、").replace(";", "、").split("、"):
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                values.append(cleaned)
    return "、".join(values)


def choose_category(current, incoming):
    def priority(category):
        if not category or category == "nan":
            return -1
        if category == "决策型":
            return 5
        if category.endswith("型"):
            return 4
        if category in {"地理位置", "锚点词"}:
            return 3
        if category in {"气象与气候", "水文地理", "人文与经济地理", "地理过程与原理", "土壤与植被", "地形与地貌"}:
            return 2
        return 1

    return incoming if priority(incoming) > priority(current) else current


def split_text_fragments(text):
    cleaned_text = str(text or "").strip()
    if not cleaned_text:
        return []

    normalized = re.sub(r"[（）()【】\\[\\]]", " ", cleaned_text)
    fragments = [cleaned_text]

    for chunk in re.split(r"[，,；;、。]", normalized):
        piece = chunk.strip(" ：: ")
        if len(piece) >= 2 and piece not in FRAGMENT_BLACKLIST:
            fragments.append(piece)
        for sub_piece in re.split(r"(?:和|及|与|并且|且|以及|或者|或)", piece):
            sub_piece = sub_piece.strip(" ：: ")
            if len(sub_piece) >= 2 and sub_piece not in FRAGMENT_BLACKLIST:
                fragments.append(sub_piece)

    seen = set()
    ordered = []
    for fragment in fragments:
        if fragment not in seen:
            seen.add(fragment)
            ordered.append(fragment)
    return ordered


def text_similarity(text_a, text_b):
    normalized_a = normalize_text(text_a)
    normalized_b = normalize_text(text_b)
    if not normalized_a or not normalized_b:
        return 0.0
    if normalized_a == normalized_b:
        return 1.0
    if normalized_a in normalized_b or normalized_b in normalized_a:
        return min(len(normalized_a), len(normalized_b)) / max(len(normalized_a), len(normalized_b))

    set_a = set(normalized_a)
    set_b = set(normalized_b)
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def add_entry(entries, keyword, category="", parent="", child=""):
    cleaned_keyword = str(keyword).strip()
    if not cleaned_keyword or cleaned_keyword == "nan":
        return

    incoming = {
        "关键字": cleaned_keyword,
        "分类": str(category or "").strip(),
        "上级": str(parent or "").strip(),
        "下级": str(child or "").strip(),
    }

    if cleaned_keyword not in entries:
        entries[cleaned_keyword] = incoming
        return

    existing = entries[cleaned_keyword]
    existing["分类"] = choose_category(existing.get("分类", ""), incoming["分类"])
    existing["上级"] = merge_delimited_values(existing.get("上级", ""), incoming["上级"])
    existing["下级"] = merge_delimited_values(existing.get("下级", ""), incoming["下级"])


def load_dictionary(path, entries):
    if not os.path.exists(path):
        return

    df = pd.read_csv(path)
    for row in df.itertuples(index=False):
        add_entry(
            entries,
            getattr(row, "关键字", ""),
            getattr(row, "分类", ""),
            getattr(row, "上级", ""),
            getattr(row, "下级", ""),
        )


def enrich_from_questions(entries, questions, default_category):
    for question in questions:
        options = question.get("options", {})
        explanation_fragments = split_text_fragments(question.get("explanation", ""))
        correct_answer = question.get("correct_answer", [])
        if isinstance(correct_answer, str):
            correct_labels = {correct_answer.strip()} if correct_answer.strip() else set()
        else:
            correct_labels = {str(label).strip() for label in correct_answer if str(label).strip()}

        for label, option_text in options.items():
            option_fragments = split_text_fragments(option_text)
            child_fragments = option_fragments[1:]

            if label in correct_labels:
                matched_explanations = [
                    fragment
                    for fragment in explanation_fragments
                    if fragment != option_text and text_similarity(fragment, option_text) >= 0.28
                ]
                child_fragments.extend(matched_explanations)

            add_entry(
                entries,
                option_text,
                "决策型",
                "题目选项",
                "、".join(child_fragments),
            )

            for fragment in option_fragments[1:]:
                add_entry(entries, fragment, default_category, option_text, "")


def save_dictionary(path, entries):
    rows = list(entries.values())
    rows.sort(key=lambda row: (row.get("关键字", ""), row.get("分类", "")))
    df = pd.DataFrame(rows, columns=["关键字", "分类", "上级", "下级"])
    df.to_csv(path, index=False, encoding="utf-8")


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    for category, csv_name in CATEGORY_FILES.items():
        multiple_dict_path = os.path.join(base_dir, "dict_multiple", csv_name)
        single_dict_path = os.path.join(base_dir, "dict_single", csv_name)
        question_path = os.path.join(base_dir, "multiple_questions", f"{category}.json")

        entries = {}
        load_dictionary(multiple_dict_path, entries)
        load_dictionary(single_dict_path, entries)

        if os.path.exists(question_path):
            with open(question_path, "r", encoding="utf-8") as f:
                questions = json.load(f).get("geography_questions", [])
            enrich_from_questions(entries, questions, DEFAULT_FRAGMENT_CATEGORIES[category])

        save_dictionary(multiple_dict_path, entries)
        print(f"{csv_name}: {len(entries)} entries")


if __name__ == "__main__":
    main()
