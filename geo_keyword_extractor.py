# geo_keyword_extractor.py
from typing import List, Dict, Tuple, Optional, Iterable
import pandas as pd
import jieba.posseg as pseg
from collections import defaultdict, Counter

class GeoKeywordExtractor:
    """
    精简实现，满足：
      - 分词与词性标注（jieba.posseg）
      - TextRank 提取关键词（选取得分高于平均分的词）
      - 领域词典（domain CSV）用于匹配/读取术语（权威）
      - 近义词表（synonym CSV 或 dict）仅用于规范化/聚合（不能扩充领域词典）
      - Rouge-N 用于比较题干与候选实体属性的相似度
    """
    _domain_cache: Dict[str, Dict[str, Dict[str, str]]] = {}
    _synonym_cache: Dict[str, Dict[str, str]] = {}

    def __init__(
        self,
        domain_csv: Optional[str] = None,
        synonym_csv: Optional[str] = None,
        synonym_dict: Optional[Dict[str, List[str]]] = None,
        stopwords: Optional[Iterable[str]] = None,
    ):
        # 领域词典：{keyword: {"分类":..., "上级":..., "下级":...}}
        self.domain = self._load_domain(domain_csv) if domain_csv else {}
        # 近义词映射：{synonym: canonical}
        self.synmap = self._load_synonyms(synonym_csv) if synonym_csv else {}
        if synonym_dict:
            self._merge_synonym_dict(synonym_dict)
        self.stopwords = set(stopwords) if stopwords else set()

    # ---------------- IO ----------------
    def _load_domain(self, path: str) -> Dict[str, Dict[str, str]]:
        if path in self._domain_cache:
            return self._domain_cache[path]

        df = pd.read_csv(path, encoding="utf-8")  # 使用默认表头处理
        dom = {}
        for row in df.itertuples(index=False):
            # 使用列名而不是位置索引，避免 pandas 警告
            k = str(row.关键字).strip() if pd.notna(row.关键字) else ""
            if not k or k == "nan":
                continue
            cat = str(row.分类).strip() if pd.notna(row.分类) else ""
            parent = str(row.上级).strip() if pd.notna(row.上级) else ""
            child = str(row.下级).strip() if pd.notna(row.下级) else ""
            if k not in dom:
                dom[k] = {"分类": cat, "上级": parent, "下级": child}
                continue

            # 多选词典里存在不少重复关键字；这里做增量合并，避免后面的行覆盖前面的决策信息。
            existing = dom[k]
            existing["分类"] = self._select_better_category(existing.get("分类", ""), cat)
            existing["上级"] = self._merge_delimited_values(existing.get("上级", ""), parent)
            existing["下级"] = self._merge_delimited_values(existing.get("下级", ""), child)
        self._domain_cache[path] = dom
        return dom

    def _select_better_category(self, current: str, incoming: str) -> str:
        def priority(category: str) -> int:
            if not category:
                return -1
            if category == "决策型":
                return 4
            if category.endswith("型"):
                return 3
            if category == "地理位置":
                return 2
            if category == "锚点词":
                return 1
            return 0

        return incoming if priority(incoming) > priority(current) else current

    def _merge_delimited_values(self, current: str, incoming: str) -> str:
        values = []
        seen = set()

        for raw in (current, incoming):
            if not raw or raw == "nan":
                continue
            parts = [item.strip() for item in str(raw).replace("；", "、").replace(";", "、").split("、") if item.strip()]
            for item in parts:
                if item not in seen:
                    seen.add(item)
                    values.append(item)

        return "、".join(values)

    def _load_synonyms(self, path: str) -> Dict[str, str]:
        if path in self._synonym_cache:
            return self._synonym_cache[path]

        df = pd.read_csv(path, encoding="utf-8")
        cols = [c.lower() for c in df.columns]
        if "canonical" in cols and "synonyms" in cols:
            cano_col = df.columns[cols.index("canonical")]
            syn_col = df.columns[cols.index("synonyms")]
        else:
            cano_col, syn_col = df.columns[0], df.columns[1]
        
        mapping: Dict[str, str] = {}
        for _, row in df.iterrows():
            cano = str(row[cano_col]).strip() if pd.notna(row[cano_col]) else ""
            if not cano:
                continue
                
            syns_field = row[syn_col]
            if pd.isna(syns_field):
                syns = [cano]
            else:
                # 支持 ; 或 , 分隔
                syns = [s.strip() for s in str(syns_field).replace(",", ";").split(";") if s.strip()]
                if cano not in syns:
                    syns.insert(0, cano)
                    
            for s in syns:
                mapping[s] = cano
            mapping[cano] = cano
        self._synonym_cache[path] = mapping
        return mapping

    def _merge_synonym_dict(self, syn: Dict[str, List[str]]):
        for cano, syns in syn.items():
            if cano not in self.synmap:
                self.synmap[cano] = cano
            for s in syns:
                self.synmap[s] = cano

    # ---------------- 分词 & 词性 ----------------
    def tokenize_pos(self, text: str) -> List[Tuple[str, str]]:
        """返回 [(word, pos), ...]"""
        return [(w.word, w.flag) for w in pseg.cut(text)]

    # ---------------- TextRank ----------------
    def _textrank(self, text: str, window: int = 4, max_iter: int = 50, d: float = 0.85, min_len: int = 2) -> Dict[str, float]:
        """基于词共现图的简单 TextRank，返回 {word: score}"""
        toks = [w for w, pos in self.tokenize_pos(text) if len(w) >= min_len and w not in self.stopwords]
        if not toks:
            return {}
            
        graph: Dict[str, set] = defaultdict(set)
        L = len(toks)
        for i, wi in enumerate(toks):
            for j in range(i+1, min(i+window, L)):
                wj = toks[j]
                if wi != wj:
                    graph[wi].add(wj); graph[wj].add(wi)
        
        if not graph:
            return {}
            
        scores = {w: 1.0 for w in graph}
        
        for _ in range(max_iter):
            new_scores = {}
            for w, nbrs in graph.items():
                s = 0.0
                for nb in nbrs:
                    denom = len(graph[nb]) if graph[nb] else 1
                    s += scores[nb] / denom
                new_scores[w] = (1 - d) + d * s
            scores = new_scores
        return scores

    def _select_by_average(self, scores: Dict[str, float]) -> List[Tuple[str, float]]:
        """选取得分高于平均分的词，按得分降序返回"""
        if not scores:
            return []
        avg = sum(scores.values()) / len(scores)
        sel = [(w, s) for w, s in scores.items() if s > avg]
        sel.sort(key=lambda x: x[1], reverse=True)
        return sel

    # ---------------- Rouge-N ----------------
    def rouge_n(self, ref_tokens: List[str], cand_tokens: List[str], n: int = 2) -> float:
        """Rouge-N = overlap(ref ngrams, cand ngrams) / total_ref_ngrams"""
        def ngrams(tokens: List[str], n: int) -> List[str]:
            if n <= 0 or len(tokens) < n:
                return []
            return [" ".join(tokens[i:i+n]) for i in range(len(tokens)-n+1)]
        r = Counter(ngrams(ref_tokens, n))
        c = Counter(ngrams(cand_tokens, n))
        total_ref = sum(r.values())
        if total_ref == 0:
            return 0.0
        overlap = sum((r & c).values())
        return overlap / total_ref

    # ---------------- 领域匹配（严格策略） ----------------
    def match_with_domain(self, token: str) -> Optional[str]:
        """
        严格匹配策略：
          1) 若 token 本身在领域词典，返回 token（优先）
          2) 否则尝试用近义词表规范化为 canonical，
             仅当 canonical 在领域词典中时返回 canonical
          3) 否则返回 None
        说明：近义词表仅用于规范化（不会扩充或改变领域词典）
        """
        t = token.strip()
        if not t:
            return None
        if t in self.domain:
            return t
        canon = self.synmap.get(t, t)
        if canon != t and canon in self.domain:
            return canon
        return None

    # ---------------- 从题干提取关键词（主接口） ----------------
    def extract_keywords(self, text: str, top_k: int = 10, allow_pos: Optional[Iterable[str]] = None) -> List[str]:
        """
        步骤（按你论文要求）：
          1) 分词+词性标注 -> 词列表
          2) TextRank 得分
          3) 选取得分高于平均分的词（作为关键词候选）
          4) 对候选词按严格匹配策略尝试映射到领域词典（先精确，再 canonical）
          5) 若映射不足 top_k，则补充 TextRank 中得分最高的词（并对这些词做规范化用于聚合）
        返回：关键词列表（去重、按优先级）
        """
        # 分词并可按词性过滤（若传入 allow_pos）
        tokens_pos = self.tokenize_pos(text)
        tokens = []
        for w, pos in tokens_pos:
            if allow_pos and pos not in allow_pos:
                continue
            if w in self.stopwords:
                continue
            tokens.append(w)

        # TextRank 得分
        scores = self._textrank(" ".join(tokens))  # join 只是形式化输入
        selected = self._select_by_average(scores)  # [(word, score)]
        # 候选词序列（按 score 降序）
        cand_words = [w for w, _ in selected]
        # 若没有高于平均的词，退回前 top_k 的 TextRank 结果
        if not cand_words:
            cand_words = [w for w, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)][:top_k*2]

        result = []
        seen = set()
        # 先把能匹配到领域词典的词加入（优先）
        for w in cand_words:
            if len(result) >= top_k:
                break
            m = self.match_with_domain(w)
            if m and m not in seen:
                result.append(m); seen.add(m)

        # 补充：若不足 top_k，则用 TextRank 原词（规范化后去重）补齐
        if len(result) < top_k:
            for w, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True):
                if len(result) >= top_k:
                    break
                norm = self.synmap.get(w, w)
                if norm not in seen:
                    result.append(norm); seen.add(norm)

        return result[:top_k]

    # ---------------- 提取与实体属性的相似属性 ----------------
    def find_relevant_entity_attributes(
        self,
        question: str,
        entity_features: Dict[str, List[str]],
        ngram: int = 2,
        top_attrs_per_entity: int = 3
    ) -> Dict[str, List[Tuple[str, float]]]:
        """
        对每个实体（entity_features: {entity_name: [attr_text1, attr_text2,...] }）
        计算候选属性与题干的 Rouge-N，相似度高的属性被视为实体的相关属性。
        返回: {entity_name: [(attr_text, score), ... (按 score 降序)]}
        """
        q_tokens = [w for w, _ in self.tokenize_pos(question)]
        out = {}
        for ent, attrs in entity_features.items():
            scored = []
            for a in attrs:
                a_tokens = [w for w, _ in self.tokenize_pos(a)]
                score = self.rouge_n(q_tokens, a_tokens, n=ngram)
                scored.append((a, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            out[ent] = scored[:top_attrs_per_entity]
        return out

    # ---------------- 小工具 ----------------
    def domain_entry(self, term: str) -> Optional[Dict[str, str]]:
        """返回领域词典中 term 的条目（若存在）"""
        return self.domain.get(term)
