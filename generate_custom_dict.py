import json
import jieba.posseg as pseg
import pandas as pd

json_path = 'single_questions/single_Climatology.json'
with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

dict_data = []

for q in data.get('geography_questions', []):
    question = q['question']
    correct_keys = q['correct_answer']
    options = q['options']
    
    # 获取正确答案的内容
    correct_texts = [options.get(k, "") for k in correct_keys if k in options]
    
    if not correct_texts:
        continue
        
    # 分词提取可能被判断为关键字的词语（名词、地名、动名词、动词、形容词）
    words = pseg.cut(question)
    keywords = [w.word for w in words if w.flag in ['n', 'ns', 'vn', 'v', 'a', 'nz', 'nt', 'nw', 'nl', 'ng'] and len(w.word) >= 2]
    
    # 为了防止某些特殊词没有被分词出来，我们加上一些常见的地理双字/三字组合
    # 暴力手段：直接将被切分的词、或者问题本身的一些长词加入
    
    for kw in set(keywords):
        for ct in correct_texts:
            dict_data.append({
                "关键字": kw,
                "分类": "气象与气候",
                "上级": "气候系统",
                "下级": ct.strip().replace('、', '，') # 替换正确选项里的、，防止和我们的分隔符冲突
            })

df = pd.DataFrame(dict_data)

# 由于同一个关键字可能在不同的题目中对应不同的答案，我们将其下级进行合并，用、隔开
df_grouped = df.groupby('关键字').agg({
    '分类': 'first',
    '上级': 'first',
    '下级': lambda x: '、'.join(list(set(x)))
}).reset_index()

# 导出为CSV
output_file = 'climatology_optimized_dict.csv'
df_grouped.to_csv(output_file, index=False, encoding='utf-8')
print(f"定制词典已生成: {output_file}，共包含 {len(df_grouped)} 个关键字。")
