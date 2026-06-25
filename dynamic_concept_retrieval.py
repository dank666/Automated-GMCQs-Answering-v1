# dynamic_concept_retrieval.py
# -*- coding: utf-8 -*-
"""
动态概念检索（Dynamic Concept Retrieval, DCR）模块

功能：
  1. 检测词典中缺失的词条
  2. 通过大语言模型动态获取相关知识
  3. 结构化地提取概念信息（分类、上级、下级）
  4. 自动更新词典文件
  5. 支持本地缓存和异步处理
"""

import json
import csv
import os
import re
import logging
import hashlib
from typing import Dict, List, Tuple, Optional, Any
from abc import ABC, abstractmethod
from datetime import datetime
from collections import defaultdict
import threading

import pandas as pd

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """大语言模型提供者的抽象基类"""
    
    @abstractmethod
    def query(self, prompt: str, **kwargs) -> str:
        """
        查询LLM
        Args:
            prompt: 提示词
        Returns:
            LLM的响应文本
        """
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API提供者"""
    
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo", temperature: float = 0.7):
        """
        初始化OpenAI提供者
        Args:
            api_key: OpenAI API密钥
            model: 模型名称
            temperature: 温度参数
        """
        try:
            import openai
            if hasattr(openai, "OpenAI"):
                self.client = openai.OpenAI(api_key=api_key)
                self._use_modern_client = True
            else:
                self.client = openai
                self.client.api_key = api_key
                self._use_modern_client = False
        except ImportError:
            logger.error("需要安装 openai 库: pip install openai")
            raise
        
        self.model = model
        self.temperature = temperature
    
    def query(self, prompt: str, **kwargs) -> str:
        """查询OpenAI API"""
        try:
            if self._use_modern_client:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=kwargs.get("max_tokens", 1000)
                )
                return response.choices[0].message.content

            response = self.client.ChatCompletion.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=kwargs.get("max_tokens", 1000)
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {e}")
            raise


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API提供者"""
    
    def __init__(self, api_key: str, model: str = "claude-3-opus-20240229"):
        """
        初始化Anthropic提供者
        Args:
            api_key: Anthropic API密钥
            model: 模型名称
        """
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            logger.error("需要安装 anthropic 库: pip install anthropic")
            raise
        
        self.model = model
    
    def query(self, prompt: str, **kwargs) -> str:
        """查询Anthropic Claude API"""
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=kwargs.get("max_tokens", 1000),
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API 调用失败: {e}")
            raise


class LocalLLMProvider(LLMProvider):
    """本地LLM提供者（通过ollama等工具）"""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2"):
        """
        初始化本地LLM提供者
        Args:
            base_url: 本地LLM服务的基础URL
            model: 模型名称
        """
        try:
            import requests
            self.requests = requests
        except ImportError:
            logger.error("需要安装 requests 库: pip install requests")
            raise
        
        self.base_url = base_url
        self.model = model
    
    def query(self, prompt: str, **kwargs) -> str:
        """查询本地LLM"""
        try:
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
            response = self.requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")
        except Exception as e:
            logger.error(f"本地LLM调用失败: {e}")
            raise


class DeepSeekProvider(LLMProvider):
    """DeepSeek API提供者"""
    
    def __init__(self, api_key: str, model: str = "deepseek-chat", temperature: float = 0.7):
        """
        初始化DeepSeek提供者
        Args:
            api_key: DeepSeek API密钥
            model: 模型名称（默认: deepseek-chat）
            temperature: 温度参数
        """
        api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DeepSeek API Key 未设置。请设置 DEEPSEEK_API_KEY，或通过 --api-key 传入。")

        try:
            import openai
            self.client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
        except ImportError:
            logger.error("需要安装 openai 库: pip install openai")
            raise
        
        self.model = model
        self.temperature = temperature
        self.api_key = api_key
    
    def query(self, prompt: str, **kwargs) -> str:
        """查询DeepSeek API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=kwargs.get("max_tokens", 1000)
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"DeepSeek API 调用失败: {e}")
            raise


class ConceptExtractor:
    """从LLM响应中提取结构化概念信息"""
    
    # 分类的优先级权重
    CATEGORY_PRIORITY = {
        "决策型": 4,
        "气象与气候": 3,
        "水文": 3,
        "地形地貌": 3,
        "人文地理": 3,
        "土壤与植被": 3,
        "锚点词": 2,
        "地理位置": 2,
    }
    
    @classmethod
    def extract_from_llm_response(
        cls, 
        concept: str, 
        llm_response: str,
        category_hint: str = ""
    ) -> Dict[str, Any]:
        """
        从LLM响应中提取概念信息
        Args:
            concept: 原始概念词
            llm_response: LLM的响应文本
            category_hint: 分类提示
        Returns:
            {
                "关键字": str,
                "分类": str,
                "上级": str,
                "下级": str,
                "confidence": float,
                "source": str
            }
        """
        result = {
            "关键字": concept.strip(),
            "分类": category_hint or "未分类",
            "上级": "",
            "下级": "",
            "confidence": 0.0,
            "source": "dynamic_retrieval"
        }
        
        # 清理响应
        response = llm_response.strip()
        
        # 尝试解析JSON格式（如果LLM返回JSON）
        try:
            data = json.loads(response)
            if isinstance(data, dict):
                result["分类"] = data.get("分类", data.get("category", category_hint or "未分类"))
                result["上级"] = data.get("上级", data.get("parent", ""))
                result["下级"] = data.get("下级", data.get("child", ""))
                result["confidence"] = data.get("confidence", 0.85)
                return result
        except json.JSONDecodeError:
            pass
        
        # 尝试提取结构化信息
        result = cls._extract_structured_info(concept, response, category_hint)
        
        return result
    
    @classmethod
    def _extract_structured_info(
        cls, 
        concept: str, 
        text: str, 
        category_hint: str
    ) -> Dict[str, Any]:
        """
        使用正则表达式提取结构化信息
        """
        result = {
            "关键字": concept.strip(),
            "分类": category_hint or "未分类",
            "上级": "",
            "下级": "",
            "confidence": 0.75,
            "source": "dynamic_retrieval"
        }
        
        # 提取分类
        category_patterns = [
            r"分类[：:]\s*([^\n，。]+)",
            r"Category[：:]\s*([^\n，。]+)",
            r"类别[：:]\s*([^\n，。]+)",
        ]
        for pattern in category_patterns:
            match = re.search(pattern, text)
            if match:
                cat = match.group(1).strip()
                if cat and cat != "nan":
                    result["分类"] = cat
                    result["confidence"] = min(1.0, result["confidence"] + 0.05)
                break
        
        # 提取上级概念
        parent_patterns = [
            r"上级[：:]\s*([^\n。]+)",
            r"Parent[：:]\s*([^\n。]+)",
            r"父类[：:]\s*([^\n。]+)",
            r"属于[：:]\s*([^\n。]+)",
        ]
        for pattern in parent_patterns:
            match = re.search(pattern, text)
            if match:
                parent = match.group(1).strip()
                if parent and parent != "nan":
                    result["上级"] = parent
                    result["confidence"] = min(1.0, result["confidence"] + 0.05)
                break
        
        # 提取下级概念
        child_patterns = [
            r"下级[：:]\s*([^\n。]+)",
            r"Child[：:]\s*([^\n。]+)",
            r"子类[：:]\s*([^\n。]+)",
            r"包括[：:]\s*([^\n。]+)",
            r"例如[：:]\s*([^\n。]+)",
        ]
        for pattern in child_patterns:
            match = re.search(pattern, text)
            if match:
                child = match.group(1).strip()
                if child and child != "nan":
                    result["下级"] = child
                    result["confidence"] = min(1.0, result["confidence"] + 0.05)
                break
        
        return result


class DynamicConceptRetriever:
    """
    动态概念检索主类
    
    集成LLM查询、概念提取、词典更新等功能
    """
    
    def __init__(
        self,
        domain_csv: str,
        llm_provider: Optional[LLMProvider] = None,
        cache_dir: Optional[str] = None,
        auto_update: bool = True,
        max_retries: int = 3,
        batch_size: int = 10
    ):
        """
        初始化动态概念检索器
        Args:
            domain_csv: 领域词典CSV文件路径
            llm_provider: LLM提供者实例
            cache_dir: 本地缓存目录
            auto_update: 是否自动更新词典
            max_retries: 最大重试次数
            batch_size: 批处理大小
        """
        self.domain_csv = domain_csv
        self.llm_provider = llm_provider
        self.cache_dir = cache_dir or os.path.join(os.path.dirname(domain_csv), ".dcr_cache")
        self.auto_update = auto_update
        self.max_retries = max_retries
        self.batch_size = batch_size
        
        # 创建缓存目录
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 加载词典
        self.domain = self._load_domain_dict()
        
        # 初始化缓存
        self.local_cache = self._load_local_cache()
        
        # 初始化统计信息
        self.stats = {
            "queried": 0,
            "cached": 0,
            "added": 0,
            "failed": 0
        }
        
        # 线程锁（用于词典更新）
        self.update_lock = threading.Lock()
        
        logger.info(f"初始化DCR: 词典路径={domain_csv}, 缓存目录={self.cache_dir}")
    
    def _load_domain_dict(self) -> Dict[str, Dict[str, str]]:
        """加载领域词典"""
        try:
            df = pd.read_csv(self.domain_csv, encoding="utf-8")
            dom = {}
            for row in df.itertuples(index=False):
                k = str(row.关键字).strip() if pd.notna(row.关键字) else ""
                if not k or k == "nan":
                    continue
                cat = str(row.分类).strip() if pd.notna(row.分类) else ""
                parent = str(row.上级).strip() if pd.notna(row.上级) else ""
                child = str(row.下级).strip() if pd.notna(row.下级) else ""
                dom[k] = {"分类": cat, "上级": parent, "下级": child}
            logger.info(f"加载词典: {len(dom)} 个词条")
            return dom
        except Exception as e:
            logger.warning(f"加载词典失败: {e}, 创建空词典")
            return {}
    
    def _load_local_cache(self) -> Dict[str, Dict[str, Any]]:
        """加载本地缓存"""
        cache_file = os.path.join(self.cache_dir, "concept_cache.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                logger.info(f"加载缓存: {len(cache)} 个条目")
                return cache
            except Exception as e:
                logger.warning(f"加载缓存失败: {e}")
        return {}
    
    def _save_local_cache(self):
        """保存本地缓存"""
        cache_file = os.path.join(self.cache_dir, "concept_cache.json")
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(self.local_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
    
    def is_missing(self, concept: str) -> bool:
        """
        检查概念是否在词典中缺失
        Args:
            concept: 概念词
        Returns:
            True 如果缺失
        """
        return concept.strip() not in self.domain
    
    def retrieve_concept(self, concept: str, context: str = "") -> Optional[Dict[str, str]]:
        """
        检索概念信息（如果缺失则调用LLM）
        Args:
            concept: 概念词
            context: 上下文信息（用于改进LLM查询）
        Returns:
            概念字典 {"分类": ..., "上级": ..., "下级": ...} 或 None
        """
        concept_clean = concept.strip()
        context_clean = str(context or "").strip()
        cache_key = concept_clean
        if context_clean:
            context_hash = hashlib.md5(context_clean.encode("utf-8")).hexdigest()[:12]
            cache_key = f"{concept_clean}@@{context_hash}"
        
        # 检查词典中是否存在
        if concept_clean in self.domain:
            return self.domain[concept_clean]
        
        # 检查本地缓存
        if cache_key in self.local_cache:
            self.stats["cached"] += 1
            logger.info(f"从缓存获取: {concept_clean}")
            return self._extract_domain_entry(self.local_cache[cache_key])
        
        # 如果没有LLM提供者，返回None
        if self.llm_provider is None:
            logger.warning(f"词典缺失且无LLM提供者: {concept_clean}")
            return None
        
        # 调用LLM查询
        logger.info(f"调用LLM查询: {concept_clean}")
        result = self._query_llm(concept_clean, context)
        
        if result:
            self.stats["queried"] += 1
            
            # 保存到本地缓存
            self.local_cache[cache_key] = result
            self._save_local_cache()
            
            # 如果启用自动更新，更新词典
            if self.auto_update:
                self._update_dictionary(concept_clean, result)
            
            return self._extract_domain_entry(result)
        else:
            self.stats["failed"] += 1
            logger.warning(f"LLM查询失败: {concept_clean}")
            return None
    
    def _query_llm(self, concept: str, context: str = "") -> Optional[Dict[str, Any]]:
        """
        调用LLM查询概念信息
        Args:
            concept: 概念词
            context: 上下文
        Returns:
            结构化概念信息或None
        """
        prompt = self._build_prompt(concept, context)
        
        for attempt in range(self.max_retries):
            try:
                response = self.llm_provider.query(prompt, max_tokens=500)
                
                # 提取结构化信息
                result = ConceptExtractor.extract_from_llm_response(
                    concept, 
                    response,
                    category_hint=self._guess_category(concept)
                )
                try:
                    confidence = float(result.get("confidence", 0.0) or 0.0)
                except (TypeError, ValueError):
                    confidence = 0.0

                if confidence < 0.5:
                    logger.info(f"LLM返回低置信度，跳过: {concept}, 置信度={confidence:.2f}")
                    return None
                
                result["confidence"] = confidence
                logger.info(f"LLM查询成功: {concept}, 置信度={confidence:.2f}")
                return result
            except Exception as e:
                logger.warning(f"LLM查询第{attempt+1}次失败: {e}")
                if attempt == self.max_retries - 1:
                    return None
        
        return None
    
    def _build_prompt(self, concept: str, context: str = "") -> str:
        """
        构建LLM提示词
        Args:
            concept: 概念词
            context: 上下文
        Returns:
            提示词字符串
        """
        prompt = f"""你正在为地理选择题自动解答系统补充领域词典。
请根据“概念”和“上下文”生成能直接帮助选项判断的结构化词典条目。

概念: {concept}
上下文: {context if context else '（无）'}

要求：
1. 分类必须从以下集合中选择最贴切的一项：气象与气候、水文、地形地貌、人文地理、土壤与植被、地理位置、锚点词、决策型。
2. “上级”填写该词在地理知识网络中的父类、机制、影响因素或所属主题，尽量贴近当前题目。
3. “下级”填写能和题干/选项发生匹配的具体表现、例子、后果、相近概念或判别线索。
4. 上级和下级都用短语，多个短语用“、”分隔；不要写长句解释。
5. 如果该词只是普通功能词、泛动词或无法提供地理判别价值，请将 confidence 设为 0.2，并尽量留空上级/下级。

请按以下JSON格式回答（仅返回JSON，不要其他文字）：
{{
    "分类": "土壤与植被",
    "上级": "父类或影响因素",
    "下级": "具体表现、相关选项线索",
    "confidence": 0.85
}}"""
        return prompt
    
    def _guess_category(self, concept: str) -> str:
        """
        根据概念词猜测其分类
        Args:
            concept: 概念词
        Returns:
            分类字符串
        """
        concept_lower = concept.lower()
        
        # 简单的关键词匹配
        if any(w in concept for w in ["温度", "降水", "风", "气候", "气象"]):
            return "气象与气候"
        elif any(w in concept for w in ["河", "水", "降水", "径流", "洪水"]):
            return "水文"
        elif any(w in concept for w in ["山", "地形", "盆地", "高原", "平原"]):
            return "地形地貌"
        elif any(w in concept for w in ["人口", "经济", "城市", "产业", "贸易"]):
            return "人文地理"
        elif any(w in concept for w in ["土壤", "植被", "森林", "草地", "荒漠"]):
            return "土壤与植被"
        
        return "未分类"
    
    def _extract_domain_entry(self, result: Dict[str, Any]) -> Dict[str, str]:
        """
        从LLM结果提取词典条目格式
        Args:
            result: LLM查询结果
        Returns:
            词典格式 {"分类": ..., "上级": ..., "下级": ...}
        """
        return {
            "分类": result.get("分类", ""),
            "上级": result.get("上级", ""),
            "下级": result.get("下级", "")
        }
    
    def _update_dictionary(self, concept: str, info: Dict[str, Any]):
        """
        更新词典文件
        Args:
            concept: 概念词
            info: 概念信息
        """
        with self.update_lock:
            try:
                # 更新内存中的词典
                self.domain[concept] = self._extract_domain_entry(info)
                
                # 追加到CSV文件
                self._append_to_csv(concept, info)
                
                self.stats["added"] += 1
                logger.info(f"词典已更新: {concept}")
            except Exception as e:
                logger.error(f"词典更新失败: {e}")
    
    def _append_to_csv(self, concept: str, info: Dict[str, Any]):
        """
        将新词条追加到CSV文件
        Args:
            concept: 概念词
            info: 概念信息
        """
        new_row = {
            "关键字": concept,
            "分类": info.get("分类", ""),
            "上级": info.get("上级", ""),
            "下级": info.get("下级", "")
        }
        
        # 读取现有数据
        try:
            df = pd.read_csv(self.domain_csv, encoding="utf-8")
        except (FileNotFoundError, pd.errors.EmptyDataError):
            df = pd.DataFrame(columns=["关键字", "分类", "上级", "下级"])
        
        # 检查是否已存在
        if concept not in df["关键字"].values:
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_csv(self.domain_csv, index=False, encoding="utf-8")
    
    def batch_retrieve(self, concepts: List[str]) -> Dict[str, Optional[Dict[str, str]]]:
        """
        批量检索概念（可能使用并行处理）
        Args:
            concepts: 概念列表
        Returns:
            {概念: 词典条目} 字典
        """
        results = {}
        
        for i, concept in enumerate(concepts):
            if i > 0 and i % self.batch_size == 0:
                logger.info(f"进度: {i}/{len(concepts)}")
            
            results[concept] = self.retrieve_concept(concept)
        
        return results
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self.stats.copy()
    
    def print_stats(self):
        """打印统计信息"""
        logger.info("=== 动态概念检索统计 ===")
        logger.info(f"LLM查询次数: {self.stats['queried']}")
        logger.info(f"缓存命中: {self.stats['cached']}")
        logger.info(f"新增词条: {self.stats['added']}")
        logger.info(f"查询失败: {self.stats['failed']}")


# ==================== 便捷工厂函数 ====================

def create_retriever(
    domain_csv: str,
    llm_config: Optional[Dict[str, Any]] = None,
    cache_dir: Optional[str] = None,
    **kwargs
) -> DynamicConceptRetriever:
    """
    创建DCR实例的便捷工厂函数
    Args:
        domain_csv: 词典CSV路径
        llm_config: LLM配置字典
            {
                "provider": "openai|anthropic|local",
                "api_key": "...",
                "model": "...",
                "base_url": "..."  # 仅用于local
            }
        cache_dir: 缓存目录
        **kwargs: 传递给DynamicConceptRetriever的其他参数
    Returns:
        DynamicConceptRetriever实例
    """
    llm_provider = None
    
    if llm_config:
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
        else:
            logger.warning(f"未知的LLM提供者类型: {provider_type}")
    
    return DynamicConceptRetriever(
        domain_csv=domain_csv,
        llm_provider=llm_provider,
        cache_dir=cache_dir,
        **kwargs
    )


if __name__ == "__main__":
    # 示例用法
    import sys
    
    # 示例1: 创建本地检索器（无LLM，仅使用缓存）
    print("示例1: 本地检索器")
    retriever = DynamicConceptRetriever(
        domain_csv="dict_single/Climatology.csv"
    )
    print(f"词典加载: {len(retriever.domain)} 个词条")
    print(f"缓存加载: {len(retriever.local_cache)} 个条目")
    
    # 示例2: 使用OpenAI（需要配置）
    print("\n示例2: 使用OpenAI")
    # retriever = create_retriever(
    #     domain_csv="dict_single/Climatology.csv",
    #     llm_config={
    #         "provider": "openai",
    #         "api_key": os.environ.get("OPENAI_API_KEY"),
    #         "model": "gpt-3.5-turbo"
    #     }
    # )
