# geo_keyword_extractor_dcr_integration.py
# -*- coding: utf-8 -*-
"""
集成动态概念检索（DCR）的地理关键词提取器增强版本

提供以下功能：
  1. 在提取关键词后，检测词典缺失的词条
  2. 调用DCR自动补充缺失的概念
  3. 支持上下文感知的概念检索
  4. 统计缺失词条和补充情况
"""

import logging
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime

try:
    from geo_keyword_extractor import GeoKeywordExtractor
    from dynamic_concept_retrieval import (
        DynamicConceptRetriever,
        create_retriever,
        LLMProvider
    )
except ImportError:
    raise ImportError("需要导入 geo_keyword_extractor 和 dynamic_concept_retrieval 模块")

logger = logging.getLogger(__name__)


@dataclass
class KeywordStats:
    """关键词提取统计"""
    total_keywords: int = 0
    domain_matched: int = 0
    missing_detected: int = 0
    dcr_retrieved: int = 0
    dcr_cached: int = 0
    dcr_failed: int = 0
    
    def __str__(self):
        return (f"关键词统计: 总数={self.total_keywords}, "
                f"词典匹配={self.domain_matched}, "
                f"缺失={self.missing_detected}, "
                f"DCR检索={self.dcr_retrieved}, "
                f"缓存命中={self.dcr_cached}, "
                f"失败={self.dcr_failed}")


class GeoKeywordExtractorWithDCR:
    """
    集成DCR的地理关键词提取器
    
    在原有GeoKeywordExtractor的基础上，增加动态概念检索能力。
    当遇到词典缺失的关键词时，自动调用DCR补充概念。
    """
    
    def __init__(
        self,
        base_extractor: Optional[GeoKeywordExtractor] = None,
        domain_csv: Optional[str] = None,
        llm_provider: Optional[LLMProvider] = None,
        enable_dcr: bool = True,
        auto_update: bool = True,
        cache_dir: Optional[str] = None,
        synonym_csv: Optional[str] = None,
        stopwords: Optional[List[str]] = None
    ):
        """
        初始化
        Args:
            base_extractor: 基础GeoKeywordExtractor实例（如果已有）
            domain_csv: 词典CSV路径（如果未提供base_extractor）
            llm_provider: LLM提供者
            enable_dcr: 是否启用DCR
            auto_update: 是否自动更新词典
            cache_dir: 缓存目录
            synonym_csv: 同义词表路径
            stopwords: 停用词列表
        """
        # 初始化基础提取器
        if base_extractor:
            self.extractor = base_extractor
        else:
            if not domain_csv:
                raise ValueError("需要提供 base_extractor 或 domain_csv")
            self.extractor = GeoKeywordExtractor(
                domain_csv=domain_csv,
                synonym_csv=synonym_csv,
                stopwords=stopwords
            )
        
        # 初始化DCR
        self.enable_dcr = enable_dcr
        self.dcr = None
        if enable_dcr:
            if not domain_csv:
                domain_csv = getattr(self.extractor, '_domain_csv', None)
            
            if domain_csv:
                self.dcr = DynamicConceptRetriever(
                    domain_csv=domain_csv,
                    llm_provider=llm_provider,
                    cache_dir=cache_dir,
                    auto_update=auto_update
                )
                logger.info(f"已初始化DCR模块（词典：{domain_csv}）")
            else:
                logger.warning("DCR启用但无法确定词典路径，DCR功能禁用")
                self.enable_dcr = False
        
        # 统计信息
        self.stats = KeywordStats()
        
        # 缺失词条历史记录
        self.missing_history: Dict[str, Dict[str, Any]] = {}
    
    def extract_keywords(
        self,
        text: str,
        top_k: int = 10,
        enable_dcr_for_missing: bool = True,
        context: str = ""
    ) -> List[str]:
        """
        提取关键词，并可选地使用DCR补充缺失词条
        Args:
            text: 输入文本
            top_k: 返回关键词数量
            enable_dcr_for_missing: 是否为缺失词条调用DCR
            context: 上下文信息（用于改进DCR查询）
        Returns:
            关键词列表
        """
        # 使用基础提取器提取关键词
        keywords = self.extractor.extract_keywords(text, top_k=top_k*2)  # 提取更多候选
        
        self.stats.total_keywords = len(keywords)
        
        result = []
        
        for keyword in keywords:
            if len(result) >= top_k:
                break
            
            # 检查是否在词典中
            entry = self.extractor.domain_entry(keyword)
            
            if entry:
                # 已在词典中
                self.stats.domain_matched += 1
                result.append(keyword)
            elif enable_dcr_for_missing and self.enable_dcr and self.dcr:
                # 尝试使用DCR检索
                logger.info(f"词典缺失，调用DCR: {keyword}")
                self.stats.missing_detected += 1
                
                retrieved_entry = self.dcr.retrieve_concept(keyword, context=context)
                
                if retrieved_entry:
                    # 获取到概念信息，仍然使用原关键词
                    result.append(keyword)
                    
                    if keyword in self.dcr.local_cache:
                        self.stats.dcr_cached += 1
                    else:
                        self.stats.dcr_retrieved += 1
                    
                    # 记录到历史
                    self._record_missing(keyword, retrieved_entry)
                else:
                    self.stats.dcr_failed += 1
                    logger.warning(f"DCR检索失败: {keyword}")
            else:
                # 无法检索，但仍然保留（可能在后续步骤处理）
                if not self.enable_dcr:
                    logger.warning(f"词典缺失且DCR未启用: {keyword}")
        
        return result[:top_k]
    
    def extract_keywords_with_enrichment(
        self,
        text: str,
        top_k: int = 10,
        context: str = ""
    ) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
        """
        提取关键词，同时返回词典条目信息
        Args:
            text: 输入文本
            top_k: 关键词数量
            context: 上下文
        Returns:
            (关键词列表, {关键词: 词典条目})
        """
        keywords = self.extract_keywords(
            text,
            top_k=top_k,
            enable_dcr_for_missing=True,
            context=context
        )
        
        enrichment = {}
        for kw in keywords:
            # 先查本地词典
            entry = self.extractor.domain_entry(kw)
            if entry:
                enrichment[kw] = entry
            elif self.dcr and kw in self.dcr.domain:
                enrichment[kw] = self.dcr.domain[kw]
        
        return keywords, enrichment
    
    def detect_missing_keywords(self, text: str) -> List[str]:
        """
        检测文本中词典缺失的关键词
        Args:
            text: 输入文本
        Returns:
            缺失关键词列表
        """
        keywords = self.extractor.extract_keywords(text, top_k=100)
        
        missing = []
        for kw in keywords:
            entry = self.extractor.domain_entry(kw)
            if not entry:
                missing.append(kw)
        
        return missing
    
    def retrieve_missing_batch(
        self,
        keywords: List[str],
        context: str = "",
        show_progress: bool = True
    ) -> Dict[str, Optional[Dict[str, str]]]:
        """
        批量检索缺失的关键词
        Args:
            keywords: 关键词列表
            context: 上下文
            show_progress: 是否显示进度
        Returns:
            {关键词: 词典条目或None} 字典
        """
        if not self.dcr:
            logger.warning("DCR未启用，无法检索缺失词条")
            return {}
        
        results = {}
        
        for i, keyword in enumerate(keywords):
            if show_progress and i % 10 == 0:
                logger.info(f"进度: {i}/{len(keywords)}")
            
            # 跳过已在词典中的词
            if self.extractor.domain_entry(keyword):
                results[keyword] = self.extractor.domain_entry(keyword)
                continue
            
            # 调用DCR
            entry = self.dcr.retrieve_concept(keyword, context=context)
            results[keyword] = entry
            
            if entry:
                self._record_missing(keyword, entry)
        
        return results
    
    def _record_missing(self, keyword: str, entry: Dict[str, str]):
        """
        记录缺失词条的处理情况
        Args:
            keyword: 关键词
            entry: 词典条目
        """
        self.missing_history[keyword] = {
            "timestamp": datetime.now().isoformat(),
            "分类": entry.get("分类", ""),
            "上级": entry.get("上级", ""),
            "下级": entry.get("下级", ""),
            "confidence": entry.get("confidence", 0.0),
            "source": entry.get("source", "unknown")
        }
    
    def get_stats(self) -> KeywordStats:
        """获取统计信息"""
        return self.stats
    
    def print_stats(self):
        """打印统计信息"""
        logger.info("="*50)
        logger.info(str(self.stats))
        if self.dcr:
            logger.info(f"DCR统计: {self.dcr.get_stats()}")
        logger.info("="*50)
    
    def get_missing_history(self) -> Dict[str, Dict[str, Any]]:
        """获取缺失词条的历史记录"""
        return self.missing_history.copy()
    
    def export_missing_concepts(self, output_path: str):
        """
        导出缺失词条的处理结果
        Args:
            output_path: 输出文件路径
        """
        import json
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.missing_history, f, ensure_ascii=False, indent=2)
        
        logger.info(f"缺失词条已导出到: {output_path}")


# ==================== 便捷工厂函数 ====================

def create_extractor_with_dcr(
    domain_csv: str,
    synonym_csv: Optional[str] = None,
    stopwords: Optional[List[str]] = None,
    llm_config: Optional[Dict[str, Any]] = None,
    cache_dir: Optional[str] = None,
    enable_dcr: bool = True,
    auto_update: bool = True
) -> GeoKeywordExtractorWithDCR:
    """
    创建集成DCR的关键词提取器
    Args:
        domain_csv: 词典CSV路径
        synonym_csv: 同义词表路径
        stopwords: 停用词列表
        llm_config: LLM配置（与dynamic_concept_retrieval.create_retriever兼容）
        cache_dir: 缓存目录
        enable_dcr: 是否启用DCR
        auto_update: 是否自动更新词典
    Returns:
        GeoKeywordExtractorWithDCR实例
    """
    # 创建基础提取器
    base_extractor = GeoKeywordExtractor(
        domain_csv=domain_csv,
        synonym_csv=synonym_csv,
        stopwords=stopwords
    )
    
    # 创建LLM提供者
    llm_provider = None
    if enable_dcr and llm_config:
        from dynamic_concept_retrieval import (
            OpenAIProvider, AnthropicProvider, LocalLLMProvider, DeepSeekProvider
        )
        
        provider_type = llm_config.get("provider", "").lower()
        
        if provider_type == "openai":
            llm_provider = OpenAIProvider(
                api_key=llm_config.get("api_key"),
                model=llm_config.get("model", "gpt-3.5-turbo"),
                temperature=llm_config.get("temperature", 0.7)
            )
        elif provider_type == "anthropic":
            llm_provider = AnthropicProvider(
                api_key=llm_config.get("api_key"),
                model=llm_config.get("model", "claude-3-opus-20240229")
            )
        elif provider_type == "deepseek":
            llm_provider = DeepSeekProvider(
                api_key=llm_config.get("api_key"),
                model=llm_config.get("model", "deepseek-chat"),
                temperature=llm_config.get("temperature", 0.7)
            )
        elif provider_type == "local":
            llm_provider = LocalLLMProvider(
                base_url=llm_config.get("base_url", "http://localhost:11434"),
                model=llm_config.get("model", "qwen2")
            )
    
    # 创建增强提取器
    return GeoKeywordExtractorWithDCR(
        base_extractor=base_extractor,
        domain_csv=domain_csv,
        llm_provider=llm_provider,
        enable_dcr=enable_dcr,
        auto_update=auto_update,
        cache_dir=cache_dir
    )


if __name__ == "__main__":
    # 示例用法
    import sys
    import os
    
    print("=== 地理关键词提取器 + DCR 示例 ===\n")
    
    # 示例1: 仅使用基础提取器（无DCR）
    print("示例1: 不启用DCR")
    try:
        extractor_no_dcr = create_extractor_with_dcr(
            domain_csv="dict_single/Climatology.csv",
            enable_dcr=False
        )
        
        text = "撒哈拉沙漠是世界上最大的沙漠，气温高，降水少。"
        keywords = extractor_no_dcr.extract_keywords(text, top_k=5)
        print(f"提取的关键词: {keywords}")
        extractor_no_dcr.print_stats()
    except Exception as e:
        print(f"示例1失败: {e}")
    
    # 示例2: 启用DCR但无LLM（使用本地缓存）
    print("\n示例2: 启用DCR（本地模式）")
    try:
        extractor_with_cache = create_extractor_with_dcr(
            domain_csv="dict_single/Climatology.csv",
            enable_dcr=True,
            llm_config=None  # 无LLM配置
        )
        
        text = "热带雨林气候全年炎热湿润。"
        keywords, enrichment = extractor_with_cache.extract_keywords_with_enrichment(
            text, 
            top_k=5,
            context="地理气候"
        )
        print(f"提取的关键词: {keywords}")
        print(f"丰富信息: {enrichment}")
        
        # 检测缺失词条
        missing = extractor_with_cache.detect_missing_keywords(text)
        if missing:
            print(f"缺失词条: {missing}")
        
        extractor_with_cache.print_stats()
    except Exception as e:
        print(f"示例2失败: {e}")
    
    print("\n=== 示例完成 ===")
