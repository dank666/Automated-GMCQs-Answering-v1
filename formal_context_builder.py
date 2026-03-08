# formal_context_builder.py
from typing import List, Dict, Tuple
import numpy as np
import os

class FormalContextBuilder:
    """
    决策形式背景构建器：根据对象集和属性集构建决策形式背景
    """
    
    def __init__(self, decision_results: Dict):
        """
        初始化
        Args:
            decision_results: DecisionContextBuilder的结果字典
        """
        # 获取所有属性和选项信息
        all_attributes = list(decision_results['attribute_set'])
        options = decision_results.get('options', [])
        
        # 通用的属性分离方法：根据选项数量动态确定决策属性数量
        if options:
            # 计算选项组合的数量：C(n,1) + C(n,2) + ... + C(n,n) = 2^n - 1
            # 但这里我们实际生成的是所有组合，包括单个选项和多选项组合
            from itertools import combinations
            decision_attr_count = 0
            for r in range(1, len(options) + 1):
                decision_attr_count += len(list(combinations(options, r)))
            
            print(f"选项数量: {len(options)}, 决策属性数量: {decision_attr_count}")
            
            # 后面的决策属性数量个属性是决策属性，前面的是条件属性
            if len(all_attributes) >= decision_attr_count:
                # 保持原有顺序，不需要重新排序，因为entity_attribute已经正确排序了
                self.condition_attributes = all_attributes[:-decision_attr_count]
                self.decision_attributes = all_attributes[-decision_attr_count:]
            else:
                # 如果属性总数不足，全部作为决策属性
                self.condition_attributes = []
                self.decision_attributes = all_attributes
        else:
            # 如果没有选项信息，使用默认方法：检查属性是否包含组合符号
            condition_attrs = []
            decision_attrs = []
            
            for attr in all_attributes:
                # 如果属性包含+号，认为是决策属性组合
                if '+' in attr:
                    decision_attrs.append(attr)
                else:
                    # 检查是否为单个选项
                    decision_attrs.append(attr)
            
            # 简单启发：假设最后的属性是决策属性
            # 这里需要更智能的判断，暂时使用简单方法
            total_attrs = len(all_attributes)
            estimated_decision_count = len([attr for attr in all_attributes if '+' in attr or len(attr) <= 3])
            
            if estimated_decision_count > 0:
                self.condition_attributes = all_attributes[:-estimated_decision_count]
                self.decision_attributes = all_attributes[-estimated_decision_count:]
            else:
                # 默认情况：所有属性都作为条件属性
                self.condition_attributes = all_attributes
                self.decision_attributes = []
        
        # 存储分离的属性信息
        
        # 重新组织属性顺序：条件属性在前，决策属性在后
        self.attributes = self.condition_attributes + self.decision_attributes
        # 确保对象顺序一致：按字母顺序排序
        self.objects = sorted(list(decision_results['object_set']))
        self.domain = decision_results.get('domain_info', {})  # 领域词典信息
        
        # 创建对象和属性的索引映射
        self.object_to_index = {obj: i for i, obj in enumerate(self.objects)}
        self.attribute_to_index = {attr: i for i, attr in enumerate(self.attributes)}
        
        # 创建分离属性的索引映射
        self.condition_attr_indices = [self.attribute_to_index[attr] for attr in self.condition_attributes]
        self.decision_attr_indices = [self.attribute_to_index[attr] for attr in self.decision_attributes]
        
        print(f"对象数量: {len(self.objects)}")
        print(f"属性数量: {len(self.attributes)}")
    
    def build_incidence_matrix(self, extractor) -> np.ndarray:
        """
        构建关联矩阵（01矩阵）
        
        Args:
            extractor: GeoKeywordExtractor实例，用于获取领域词典信息
            
        Returns:
            numpy数组，形状为(对象数, 属性数)
        """
        matrix = np.zeros((len(self.objects), len(self.attributes)), dtype=int)
        
        for i, obj in enumerate(self.objects):
            for j, attr in enumerate(self.attributes):
                # 判断对象是否拥有属性
                has_attribute = self._object_has_attribute(obj, attr, extractor)
                matrix[i][j] = 1 if has_attribute else 0
        
        return matrix
    
    def _object_has_attribute(self, obj: str, attr: str, extractor) -> bool:
        """
        判断对象是否拥有某个属性
        
        Args:
            obj: 对象名称
            attr: 属性名称
            extractor: GeoKeywordExtractor实例
            
        Returns:
            bool: True表示对象拥有该属性
        """
        # 1. 如果对象和属性相同，则拥有
        if obj == attr:
            return True
        
        # 2. 检查对象在领域词典中的信息
        obj_info = extractor.domain.get(obj, {})
        
        # 3. 检查属性是否在对象的下级信息中
        obj_children = obj_info.get('下级', '')
        if obj_children and attr in obj_children.split('、'):
            return True
        
        # 4. 检查属性是否在对象的上级信息中
        obj_parent = obj_info.get('上级', '')
        if obj_parent and attr == obj_parent:
            return True
        
        # 5. 检查属性是否在对象的同级信息中（通过共同上级判断）
        attr_info = extractor.domain.get(attr, {})
        attr_parent = attr_info.get('上级', '')
        if obj_parent and attr_parent and obj_parent == attr_parent and obj != attr:
            return True
        
        # 6. 检查分类关系
        obj_category = obj_info.get('分类', '')
        attr_category = attr_info.get('分类', '')
        if obj_category and attr_category and obj_category == attr_category:
            return True
        
        # 7. 特殊规则：地理实体与其所在区域的关系
        # 例如：青藏高原 拥有 高原、地形等属性
        if self._check_geographical_relationship(obj, attr, extractor):
            return True
        
        # 8. 检查决策属性：如果属性是决策属性（包含+号），需要特殊处理
        if '+' in attr:
            # 对于组合决策属性，要求对象必须同时拥有所有部分
            parts = attr.split('+')
            for part in parts:
                if not self._object_has_simple_attribute(obj, part.strip(), extractor):
                    return False  # 只要有一个部分不拥有，就返回False
            return True  # 所有部分都拥有才返回True
        else:
            # 对于单一决策属性，检查对象是否与该属性相关
            if self._object_has_simple_attribute(obj, attr, extractor):
                return True
        
        return False
    
    def _check_geographical_relationship(self, obj: str, attr: str, extractor) -> bool:
        """
        检查地理实体间的特殊关系
        """
        obj_info = extractor.domain.get(obj, {})
        attr_info = extractor.domain.get(attr, {})
        
        # 如果对象是具体地理实体，属性是地理类型
        obj_parent = obj_info.get('上级', '')
        if obj_parent == attr:  # 例如：青藏高原的上级是高原
            return True
        
        # 如果对象的上级的上级是属性
        if obj_parent:
            parent_info = extractor.domain.get(obj_parent, {})
            grandparent = parent_info.get('上级', '')
            if grandparent == attr:  # 例如：青藏高原->高原->地形
                return True
        
        return False
    
    def _object_has_simple_attribute(self, obj: str, attr: str, extractor) -> bool:
        """
        检查对象是否拥有简单属性（非组合属性）
        """
        obj_info = extractor.domain.get(obj, {})
        
        # 检查层次关系
        obj_parent = obj_info.get('上级', '')
        obj_children = obj_info.get('下级', '')
        
        # 如果对象的上级是属性，或属性是对象的下级
        if obj_parent == attr or (obj_children and attr in obj_children.split('、')):
            return True
        
        # 检查传递关系：如果对象是地形实体，则拥有相应的地形类型属性
        if attr in ['高原', '平原', '盆地', '山地', '丘陵']:
            if obj_parent == attr:  # 直接的上下级关系
                return True
            # 检查更深层次的关系
            if obj_parent:
                parent_info = extractor.domain.get(obj_parent, {})
                if parent_info.get('上级') == attr:
                    return True
        
        return False
    
    def save_formal_context(self, matrix: np.ndarray, filename: str):
        """
        保存决策形式背景到文件
        
        Args:
            matrix: 关联矩阵
            filename: 输出文件名
        """
        with open(filename, 'w', encoding='utf-8') as f:
            # 第一行：对象个数
            f.write(f"{len(self.objects)}\n")
            # 第二行：属性个数
            f.write(f"{len(self.attributes)}\n")
            # 从第三行开始：01矩阵
            for row in matrix:
                f.write(''.join(map(str, row)) + '\n')
        
        print(f"\n决策形式背景已保存到: {filename}")
    
    def save_csv_matrix(self, matrix: np.ndarray, filename: str):
        """
        保存带标签的CSV格式矩阵
        
        Args:
            matrix: 关联矩阵
            filename: 输出文件名
        """
        import csv
        
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            
            # 写入标题行：第一列空白，然后是所有属性名
            header = ['对象\\属性'] + self.attributes
            writer.writerow(header)
            
            # 写入数据行：第一列是对象名，然后是对应的01值
            for i, obj in enumerate(self.objects):
                row = [obj] + list(matrix[i])
                writer.writerow(row)
        
        print(f"CSV格式矩阵已保存到: {filename}")
    
    def save_condition_context(self, matrix: np.ndarray, filename: str):
        """
        保存只包含条件属性的形式背景到文件
        
        Args:
            matrix: 完整的关联矩阵
            filename: 输出文件名
        """
        # 提取条件属性对应的列
        condition_matrix = matrix[:, self.condition_attr_indices]
        
        with open(filename, 'w', encoding='utf-8') as f:
            # 第一行：对象个数
            f.write(f"{len(self.objects)}\n")
            # 第二行：条件属性个数
            f.write(f"{len(self.condition_attributes)}\n")
            # 从第三行开始：01矩阵（只包含条件属性）
            for row in condition_matrix:
                f.write(''.join(map(str, row)) + '\n')
        
        print(f"条件属性形式背景已保存到: {filename}")
    
    def save_decision_context(self, matrix: np.ndarray, filename: str):
        """
        保存只包含决策属性的形式背景到文件
        
        Args:
            matrix: 完整的关联矩阵
            filename: 输出文件名
        """
        # 提取决策属性对应的列
        decision_matrix = matrix[:, self.decision_attr_indices]
        
        with open(filename, 'w', encoding='utf-8') as f:
            # 第一行：对象个数
            f.write(f"{len(self.objects)}\n")
            # 第二行：决策属性个数
            f.write(f"{len(self.decision_attributes)}\n")
            # 从第三行开始：01矩阵（只包含决策属性）
            for row in decision_matrix:
                f.write(''.join(map(str, row)) + '\n')
        
        print(f"决策属性形式背景已保存到: {filename}")
    
    def print_context_info(self, matrix: np.ndarray):
        """
        打印决策形式背景的简要信息
        """
        # 统计信息
        total_relations = np.sum(matrix)
        total_possible = len(self.objects) * len(self.attributes)
        density = total_relations / total_possible * 100
        
        print(f"对象数量: {len(self.objects)}")
        print(f"属性数量: {len(self.attributes)}")
        print(f"关联密度: {density:.2f}% ({total_relations}/{total_possible})")
    
    def build_and_save_contexts(self, extractor, base_filename: str = "formal_context"):
        """
        构建并保存决策形式背景
        
        Args:
            extractor: GeoKeywordExtractor实例
            base_filename: 基础文件名
        """
        print("开始构建决策形式背景...")
        
        # 确保test_contexts目录存在
        output_dir = "test_contexts"
        os.makedirs(output_dir, exist_ok=True)
        
        # 构建关联矩阵
        matrix = self.build_incidence_matrix(extractor)
        
        # 打印简要信息
        self.print_context_info(matrix)
        
        # 保存决策形式背景
        context_file = os.path.join(output_dir, f"{base_filename}.txt")
        self.save_formal_context(matrix, context_file)
        
        # 保存CSV格式矩阵
        csv_file = os.path.join(output_dir, f"{base_filename}.csv")
        self.save_csv_matrix(matrix, csv_file)
        
        # 保存分离的形式背景
        condition_file = os.path.join(output_dir, f"{base_filename}_condition.txt")
        self.save_condition_context(matrix, condition_file)
        
        decision_file = os.path.join(output_dir, f"{base_filename}_decision.txt")
        self.save_decision_context(matrix, decision_file)
        
        return matrix
