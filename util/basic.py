#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Author  : yixuan yang
# @File    : basic.py
import util.vo as vo


class BasicCL:
    def __init__(self):
        self.dictAll = {}  # 全局字典
        self.objResult = set()  # 对象结果集
        self.attrResult = set()  # 属性结果集
        self.bpcAllCL = set()  # 概念格集合
        self._basis_cache = {}
        self._intersection_cache = {}

    def _normalize_index_tuple(self, values):
        if isinstance(values, int):
            return (values,)
        if isinstance(values, tuple):
            return tuple(sorted(values))
        return tuple(sorted(values))

    def _get_basis_views(self, bpc):
        cache_key = id(bpc)
        cached = self._basis_cache.get(cache_key)
        if cached is not None:
            return cached

        right_tuples = []
        right_sets = []
        for pair in bpc:
            right = tuple(pair.getR())
            right_tuples.append(right)
            right_sets.append(set(right))

        cached = (right_tuples, right_sets)
        self._basis_cache[cache_key] = cached
        return cached


    #以对象为key,该对象对应的属性集为value的全对象字典，注：也可以考虑用dict存储
    #遍历矩阵，找出每个对象具有的所有属性
    def getBPCliqueObj(self, adjMat, obj, attr, numObj, numAttr):

        tmpBpc = []

        for i in range(numObj):
            tmpList = []
            tmpObj = obj.__getitem__(i)

            for j in range(numAttr):
                if(adjMat[i][j] == 1):
                    tmpList.append(attr.__getitem__(j))

            tmpPair = vo.Pair(tmpObj, tuple(tmpList))

            tmpBpc.append(tmpPair)

        return tmpBpc  # 返回一个列表，列表中每个元素是一个Pair对象


    #以属性为key，该属性对应对象集为value的全属性字典
    #遍历矩阵，找出具有每个属性的所有对象
    def getBPCliqueAttr(self, adjMat, obj, attr, numObj, numAttr):
        tmpBpc = []

        for i in range(numAttr):
            tmpList = []
            tmpAttr = attr.__getitem__(i)

            for j in range(numObj):
                if(adjMat[j][i] == 1):
                    tmpList.append(obj.__getitem__(j))

            tmpPair = vo.Pair(tmpAttr, tuple(tmpList))
            tmpBpc.append(tmpPair)

        return tmpBpc


    #求概念格的外延集
    def objRes(self,obj,attr,bpcObj,bpcAttr):
        # 将特殊概念放入,不然后期两两做交运算会丢失外延
        spcObj = tuple(obj)
        objResult = {spcObj}
        objSetCache = {spcObj: set(spcObj)}

        _, attrObjectSets = self._get_basis_views(bpcAttr)

        for oneObj in attrObjectSets:
            current_results = tuple(objResult)
            for extent in current_results:
                temp_set = objSetCache[extent].intersection(oneObj)
                temp = tuple(sorted(temp_set))
                if temp not in objSetCache:
                    objSetCache[temp] = temp_set
                    objResult.add(temp)

        if tuple() in objResult:
            objResult.discard(tuple())
            objResult.discard(spcObj)
        self.objResult = objResult
        return objResult


    #获取每条外延所对应的内涵，obt为一条外延
    def intersectForObject(self, obt, bpcObj):
        normalized_obt = self._normalize_index_tuple(obt)
        if not normalized_obt:
            return vo.Pair(0, 0)

        cache_key = (id(bpcObj), normalized_obt)
        cached = self._intersection_cache.get(cache_key)
        if cached is not None:
            return cached

        rightTuples, rightSets = self._get_basis_views(bpcObj)

        if len(normalized_obt) == 1:
            tupTem = rightTuples[normalized_obt[0] - 1]
            tmpPair = vo.Pair(normalized_obt, tupTem) if tupTem else vo.Pair(0, 0)
            self._intersection_cache[cache_key] = tmpPair
            return tmpPair

        set1 = set(rightSets[normalized_obt[0] - 1])
        for index in normalized_obt[1:]:
            set1.intersection_update(rightSets[index - 1])
            if not set1:
                break

        tmpPair = vo.Pair(normalized_obt, tuple(sorted(set1))) if set1 else vo.Pair(0, 0)
        self._intersection_cache[cache_key] = tmpPair
        return tmpPair


        # 获取每条外延所对应的内涵，obt为一条外延

    def intersectForObj(self, obt, bpcObj):
        pair = self.intersectForObject((obt,), bpcObj)
        return pair.getR() if pair.getR() != 0 else ()


    #将外延集中所有外延的内涵求出并返回
    def finalBpcAll(self,objResult, bpcObj, bpcAttr):
        bpCliques = []
        attrResult = set()
        for obt in objResult:
            pair = self.intersectForObject(obt, bpcObj)
            if pair.getR() != 0:
                closurePair = self.intersectForObject(pair.getR(), bpcAttr)
                conceptPair = vo.Pair(closurePair.getR(), closurePair.getL())
                bpCliques.append(conceptPair)
                attrResult.add(conceptPair.getR())

        return bpCliques, attrResult

    # 将内涵集中所有内涵的外延求出并返回概念格
    def finalBpcAllforExtent(self, attrResult, bpcObj, bpcAttr):
        bpCliques = []
        objResult = set()
        for att in attrResult:
            pair = self.intersectForObject(att, bpcAttr)
            if pair.getR() == 0:
                continue
            closurePair = self.intersectForObject(pair.getR(), bpcObj)
            bpCliques.append(closurePair)
            objResult.add(closurePair.getL())

        return bpCliques, objResult
