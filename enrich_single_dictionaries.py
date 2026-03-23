import json
import os

from enrich_multiple_dictionaries import (
    CATEGORY_FILES,
    DEFAULT_FRAGMENT_CATEGORIES,
    add_entry,
    load_dictionary,
    save_dictionary,
    split_text_fragments,
    text_similarity,
)


BUILD_MODES = {
    "Climatology": "fragments",
    "Geographical Processes and Principles": "merge_multi_full",
    "Human and Economic Geography": "full",
    "Hydrology": "full",
    "Soil and Vegetation": "merge_multi_full",
    "Topography and Geomorphology": "merge_multi_full",
}


def enrich_from_single_questions(entries, questions, default_category, add_full_option):
    for question in questions:
        options = question.get("options", {})
        explanation_fragments = split_text_fragments(question.get("explanation", ""))
        correct_answer = question.get("correct_answer", [])

        if isinstance(correct_answer, str):
            correct_labels = {correct_answer.strip()} if correct_answer.strip() else set()
        else:
            correct_labels = {str(label).strip() for label in correct_answer if str(label).strip()}

        for label, option_text in options.items():
            if label not in correct_labels:
                continue

            option_fragments = split_text_fragments(option_text)
            child_fragments = option_fragments[1:]
            matched_explanations = [
                fragment
                for fragment in explanation_fragments
                if fragment != option_text and text_similarity(fragment, option_text) >= 0.28
            ]
            child_fragments.extend(matched_explanations)

            parent_text = option_text if add_full_option else ""
            if add_full_option:
                add_entry(
                    entries,
                    option_text,
                    "决策型",
                    "题目选项",
                    "、".join(child_fragments),
                )

            for fragment in option_fragments[1:]:
                add_entry(entries, fragment, default_category, parent_text, "")
            for fragment in matched_explanations:
                add_entry(entries, fragment, default_category, parent_text, "")


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    for category, csv_name in CATEGORY_FILES.items():
        mode = BUILD_MODES.get(category, "full")
        single_dict_path = os.path.join(base_dir, "dict_single", csv_name)
        multiple_dict_path = os.path.join(base_dir, "dict_multiple", csv_name)
        question_path = os.path.join(base_dir, "single_questions", f"{category}.json")

        entries = {}
        load_dictionary(single_dict_path, entries)

        if mode in {"merge_multi", "merge_multi_full"}:
            load_dictionary(multiple_dict_path, entries)

        if os.path.exists(question_path) and mode in {"fragments", "full", "merge_multi_full"}:
            with open(question_path, "r", encoding="utf-8") as f:
                questions = json.load(f).get("geography_questions", [])
            enrich_from_single_questions(
                entries,
                questions,
                DEFAULT_FRAGMENT_CATEGORIES[category],
                add_full_option=(mode in {"full", "merge_multi_full"}),
            )

        save_dictionary(single_dict_path, entries)
        print(f"{csv_name}: {len(entries)} entries ({mode})")


if __name__ == "__main__":
    main()
