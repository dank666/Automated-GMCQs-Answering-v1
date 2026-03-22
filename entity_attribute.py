# entity_attribute.py
from typing import List, Dict, Set
import jieba.posseg as pseg
import re

class EntityAttributeExtractor:
    """
    从关键词提取实体关联类集合和属性集合
    """
    
    def __init__(self, extractor):
        """
        初始化
        Args:
            extractor: 已实例化的GeoKeywordExtractor对象
        """
        self.extractor = extractor
        self.domain = extractor.domain  # 领域词典
        self._token_cache = {}
        self._similarity_cache = {}
        self._char_cache = {}

    def _get_tokens(self, text: str) -> Set[str]:
        cleaned_text = str(text).strip()
        if not cleaned_text:
            return set()

        if cleaned_text not in self._token_cache:
            self._token_cache[cleaned_text] = {w for w, _ in pseg.cut(cleaned_text)}

        return self._token_cache[cleaned_text]

    def _get_char_set(self, text: str) -> Set[str]:
        cleaned_text = str(text).strip()
        if not cleaned_text:
            return set()

        if cleaned_text not in self._char_cache:
            normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", cleaned_text)
            self._char_cache[cleaned_text] = set(normalized)

        return self._char_cache[cleaned_text]
        
    def calculate_similarity(self, entity: str, concept: str) -> float:
        """
        计算实体与概念的相似度
        使用简单的词汇重叠度计算
        """
        cache_key = tuple(sorted((str(entity).strip(), str(concept).strip())))
        if cache_key in self._similarity_cache:
            return self._similarity_cache[cache_key]

        entity_tokens = self._get_tokens(entity)
        concept_tokens = self._get_tokens(concept)
        
        if not entity_tokens or not concept_tokens:
            return 0.0
            
        # 计算Jaccard相似度：交集/并集
        intersection = len(entity_tokens & concept_tokens)
        union = len(entity_tokens | concept_tokens)
        similarity = intersection / union if union > 0 else 0.0
        self._similarity_cache[cache_key] = similarity
        return similarity
    
    def get_top_similar_concepts(self, entity: str, top_k: int = 2) -> List[str]:
        """
        为实体找到相似度排名前top_k的概念作为关联类
        """
        similarities = []
        entity_chars = self._get_char_set(entity)
        candidate_concepts = []
        
        for concept in self.domain.keys():
            if concept == entity:
                continue

            concept_chars = self._get_char_set(concept)
            if entity_chars and concept_chars and entity_chars.intersection(concept_chars):
                candidate_concepts.append(concept)
            elif entity in concept or concept in entity:
                candidate_concepts.append(concept)

        if not candidate_concepts:
            candidate_concepts = [concept for concept in self.domain.keys() if concept != entity]

        for concept in candidate_concepts:
            sim = self.calculate_similarity(entity, concept)
            similarities.append((concept, sim))
        
        # 按相似度降序排序，取前top_k个且相似度必须大于0
        similarities.sort(key=lambda x: x[1], reverse=True)
        valid_sims = [(c, s) for c, s in similarities if s > 0.0]
        return [concept for concept, _ in valid_sims[:top_k]]
    
    def get_entity_info(self, entity: str) -> Dict[str, str]:
        """
        获取实体在领域词典中的信息
        """
        return self.domain.get(entity, {"分类": "", "上级": "", "下级": ""})
    
    def extract_hierarchy_info(self, entities: List[str]) -> Set[str]:
        """
        提取实体的上级和同级信息
        """
        hierarchy_info = set()
        
        for entity in entities:
            if entity in self.domain:
                entry = self.domain[entity]
                
                # 添加上级信息
                parent = entry.get("上级", "").strip()
                if parent and parent != "":
                    # 处理多个上级（可能用顿号分隔）
                    parents = [p.strip() for p in parent.split("、") if p.strip()]
                    hierarchy_info.update(parents)
                    
                    # 查找同级：具有相同上级的其他概念
                    for other_entity, other_info in self.domain.items():
                        other_parent = other_info.get("上级", "").strip()
                        if other_parent == parent and other_entity != entity:
                            hierarchy_info.add(other_entity)
        
        return hierarchy_info
    
    def extract_subordinate_info(self, entities: List[str]) -> Set[str]:
        """
        提取实体的下级信息作为属性
        """
        subordinate_info = set()
        
        for entity in entities:
            if entity in self.domain:
                entry = self.domain[entity]
                
                # 添加下级信息
                children = entry.get("下级", "").strip()
                if children and children != "":
                    # 处理多个下级（可能用顿号分隔）
                    child_list = [c.strip() for c in children.split("、") if c.strip()]
                    subordinate_info.update(child_list)
        
        return subordinate_info
    
    def build_entity_relations_and_attributes(self, keywords: List[str], options: List[str] = None) -> Dict[str, any]:
        """
        主要方法：构建实体关联类集合和属性集合
        
        Args:
            keywords: 关键词列表
            options: 选项内容列表，如["高原", "平原", "盆地"]
        
        返回格式：
        {
            "entities": [原始关键词实体],
            "entity_related_classes": [实体关联类集合],
            "object_set": [对象集 = 实体 + 关联类 + 上级同级],
            "attribute_set": [属性集 = 下级信息 + 决策属性组合],
            "entity_relations": {实体: [其关联类]}
        }
        """
        print("=== 开始构建实体关联类集合和属性集合 ===\n")
        
        # 如果没有提供选项，使用默认的A,B,C
        if options is None:
            options = ["A", "B", "C"]
        
        result = {
            "entities": keywords.copy(),
            "entity_related_classes": set(),
            "object_set": set(),
            "attribute_set": set(),
            "entity_relations": {}
        }
        
        # 步骤1：为每个实体计算关联类
        print("步骤1：计算实体关联类")
        all_entities = set(keywords)  # 包含原始实体
        
        for i, entity in enumerate(keywords):
            print(f"  处理实体 {i+1}/{len(keywords)}: {entity}")
            
            # 获取该实体的前2个关联类
            related_concepts = self.get_top_similar_concepts(entity, top_k=2)
            result["entity_relations"][entity] = related_concepts
            result["entity_related_classes"].update(related_concepts)
            all_entities.update(related_concepts)
            
            print(f"    关联类: {related_concepts}")
        
        # 步骤2：构建四元组集合（实体在领域词典的信息）
        print(f"\n步骤2：搜索实体及关联类的领域词典信息")
        for entity in all_entities:
            if entity in self.domain:
                info = self.get_entity_info(entity)
                print(f"  {entity}: {info}")
        
        # 步骤3：检索上级与同级信息，添加到对象集（只添加与实体关系较近的上级）
        print(f"\n步骤3：检索上级与同级信息")
        
        # 为每个实体和关联类单独处理，过滤上级信息
        filtered_hierarchy_entities = set()
        
        for entity in all_entities:
            hierarchy_info = {}
            if entity in self.domain:
                # 直接从字典结构获取层次信息
                entity_data = self.domain[entity]
                hierarchy_info = {
                    '上级': [entity_data.get('上级', '')] if entity_data.get('上级') and entity_data.get('上级').strip() else [],
                    '同级': [],  # CSV中没有同级信息
                    '下级': entity_data.get('下级', '').split('、') if entity_data.get('下级') and entity_data.get('下级').strip() else []
                }
                
                # 清理空字符串
                hierarchy_info['上级'] = [x.strip() for x in hierarchy_info['上级'] if x.strip()]
                hierarchy_info['下级'] = [x.strip() for x in hierarchy_info['下级'] if x.strip()]
            
            # 对于上级信息，只添加与实体相关或重要的地理概念
            if hierarchy_info.get('上级'):
                for superior in hierarchy_info['上级']:
                    # 检查上级是否与实体相关或是重要的地理概念
                    is_relevant = False
                    
                    # 检查是否包含实体关键词
                    for keyword in keywords:
                        if any(word in superior for word in keyword.split()):
                            is_relevant = True
                            break
                    
                    # 检查是否是重要的地理概念（避免过于宽泛的上级概念）
                    important_geo_keywords = ['地形', '地貌', '地势', '地理', '形态', '地表', '山地', '平地', '高地', '低地', '高原']
                    if any(keyword in superior for keyword in important_geo_keywords):
                        is_relevant = True
                    
                    # 检查长度，避免过于简单或复杂的概念
                    if len(superior) > 10 or len(superior) < 2:
                        is_relevant = False
                        
                    if is_relevant:
                        filtered_hierarchy_entities.add(superior)
                        print(f"    添加上级概念: {entity} -> {superior}")
            
            # 添加同级信息（保持不变）
            if hierarchy_info.get('同级'):
                for peer in hierarchy_info['同级']:
                    filtered_hierarchy_entities.add(peer)
                    print(f"    添加同级概念: {entity} -> {peer}")
        
        if filtered_hierarchy_entities:
            print(f"  发现相关上级/同级概念: {filtered_hierarchy_entities}")
            all_entities.update(filtered_hierarchy_entities)
        else:
            print("  未发现相关上级/同级概念")
        
        result["object_set"] = all_entities
        
        # 步骤4：检索实体及其关联类的下级信息作为属性集
        print(f"\n步骤4：检索实体及其关联类的下级信息作为属性")
        # 只检索原始实体和关联类的下级信息，不包括上级同级概念
        entities_and_related = list(keywords) + list(result["entity_related_classes"])
        subordinate_attrs = self.extract_subordinate_info(entities_and_related)
        if subordinate_attrs:
            print(f"  发现下级概念: {subordinate_attrs}")
            result["attribute_set"].update(subordinate_attrs)
        else:
            print("  未发现下级概念")
        
        # 步骤5：添加多选题决策属性（实际选项内容的组合）
        print(f"\n步骤5：添加多选题决策属性")
        decision_attrs = self._generate_option_combinations(options)
        print(f"  决策属性: {decision_attrs}")
        
        # 转换为列表便于显示和处理
        result["entity_related_classes"] = list(result["entity_related_classes"])
        result["object_set"] = list(result["object_set"])
        
        # 确保属性顺序：条件属性在前，决策属性在后
        # 从下级概念属性中排除决策属性中已存在的单个选项
        condition_attrs = list(result["attribute_set"])  # 当前的下级概念属性
        decision_attr_set = set(decision_attrs)
        
        # 去除条件属性中与决策属性重复的部分
        filtered_condition_attrs = [attr for attr in condition_attrs if attr not in decision_attr_set]
        
        # 将属性集合重新组织：过滤后的条件属性 + 决策属性
        result["attribute_set"] = filtered_condition_attrs + decision_attrs
        
        # 添加选项信息以便后续使用
        result["options"] = options.copy() if options else []
        
        print(f"\n=== 构建完成 ===")
        return result
    
    def _generate_option_combinations(self, options: List[str]) -> List[str]:
        """
        生成选项内容的所有组合，按照单个选项、两个选项组合、三个选项组合的顺序排列
        对多选题而言，真实选项必须完整进入决策域，不能在这里被过早过滤
        
        Args:
            options: 选项内容列表，如["高原", "平原", "盆地"]
            
        Returns:
            按组合数量排序的所有可能组合，如["高原", "平原", "盆地", "高原+平原", "高原+盆地", "平原+盆地", "高原+平原+盆地"]
        """
        from itertools import combinations
        
        valid_options = []
        seen_options = set()
        for option in options:
            cleaned_option = str(option).strip()
            if not cleaned_option or cleaned_option in seen_options:
                continue

            seen_options.add(cleaned_option)
            valid_options.append(cleaned_option)

            if cleaned_option in self.domain:
                classification = self.domain[cleaned_option].get('分类', '')
                print(f"    选项 '{cleaned_option}' 分类为 '{classification}'，保留进入决策域")
            else:
                print(f"    选项 '{cleaned_option}' 不在词典中，仍保留进入决策域")
        
        print(f"  有效选项: {valid_options}")
        
        combinations_list = []
        
        for r in range(1, len(valid_options) + 1):
            for combo in combinations(valid_options, r):
                combinations_list.append('+'.join(combo))
        
        return combinations_list
    
    def _parse_hierarchy_from_description(self, description: str) -> Dict[str, List[str]]:
        """
        从描述文本中解析层次信息
        
        Args:
            description: 概念的描述文本
            
        Returns:
            包含上级、同级、下级信息的字典
        """
        hierarchy_info = {'上级': [], '同级': [], '下级': []}
        
        # 解析上级信息
        if '上级：' in description:
            upper_part = description.split('上级：')[1].split('同级：')[0] if '同级：' in description else description.split('上级：')[1].split('下级：')[0] if '下级：' in description else description.split('上级：')[1]
            upper_concepts = [concept.strip() for concept in upper_part.replace('；', ';').split(';') if concept.strip()]
            hierarchy_info['上级'] = upper_concepts
        
        # 解析同级信息  
        if '同级：' in description:
            same_part = description.split('同级：')[1].split('下级：')[0] if '下级：' in description else description.split('同级：')[1]
            same_concepts = [concept.strip() for concept in same_part.replace('；', ';').split(';') if concept.strip()]
            hierarchy_info['同级'] = same_concepts
        
        # 解析下级信息
        if '下级：' in description:
            lower_part = description.split('下级：')[1]
            lower_concepts = [concept.strip() for concept in lower_part.replace('；', ';').split(';') if concept.strip()]
            hierarchy_info['下级'] = lower_concepts
        
        return hierarchy_info
    
    def print_results(self, results: Dict[str, any]):
        """
        格式化打印结果
        """
        print("\n" + "="*60)
        print("实体关联类集合和属性集合构建结果")
        print("="*60)
        
        print(f"\n【原始实体】({len(results['entities'])}个):")
        for i, entity in enumerate(results['entities'], 1):
            print(f"  {i:2d}. {entity}")
        
        print(f"\n【实体关联类集合】({len(results['entity_related_classes'])}个):")
        for i, concept in enumerate(results['entity_related_classes'], 1):
            concept_info = self.get_entity_info(concept)
            print(f"  {i:2d}. {concept} (分类: {concept_info.get('分类', '未知')})")
        
        print(f"\n【对象集】({len(results['object_set'])}个):")
        print("  (包含: 原始实体 + 实体关联类 + 上级同级概念)")
        for i, obj in enumerate(sorted(results['object_set']), 1):
            obj_info = self.get_entity_info(obj)
            print(f"  {i:2d}. {obj} (分类: {obj_info.get('分类', '未知')})")
        
        print(f"\n【属性集】({len(results['attribute_set'])}个):")
        # 分离下级概念和决策属性（包含+号的是多选组合，单个选项也是决策属性）
        # 获取原始选项内容进行匹配
        all_attrs = results['attribute_set']
        
