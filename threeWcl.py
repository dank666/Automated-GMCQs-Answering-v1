#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Author  : yixuan yang
# @File    : threeWcl.py

import sys
import os
import numpy as np
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import util.CL as CL
import util.vo as vo
import util.basic as bs
import datetime as dt

def load_formal_context(filename):
    """
    加载形式背景文件
    """
    with open(filename, "r", encoding='utf-8') as f:
        numObj = int(f.readline())  # 获取对象数量
        numAttr = int(f.readline())  # 获取属性数量
        adjMat = np.zeros(shape=(numObj, numAttr), dtype=int)  # 存储形式背景矩阵
        adjMatC = np.zeros(shape=(numObj, numAttr), dtype=int)  # 存储补形式背景矩阵
        obj = []
        attr = []

        # 将形式背景存储到矩阵内
        for i in range(numObj):
            obj.append(i + 1)
            for j in range(numAttr):
                t = int(f.read(1))
                adjMat[i][j] = t
                adjMatC[i][j] = 1 if t == 0 else 0  # 0 和 1 背景取反
            f.read(1)  # 读取行末的换行符

        for i in range(numAttr):
            attr.append(i + 1)

        return adjMat, adjMatC, obj, attr

def _prepare_concept_views(bp):
    views = []
    for pair in bp:
        left = tuple(pair.getL())
        right = tuple(pair.getR())
        views.append((left, right, set(left), set(right)))
    return views

def _cached_tuple_set(values, cache):
    cached = cache.get(values)
    if cached is None:
        cached = set(values)
        cache[values] = cached
    return cached

def _compute_ae(bp1_views, bp2_views, bpcAttr, bpcAttrC, helper, obj, attr):
    AEC = set()
    RAE = set()
    tuple_set_cache = {}

    for left1, _, left1_set, right1_set in bp1_views:
        for left2, _, left2_set, right2_set in bp2_views:
            shared_attrs = right1_set.intersection(right2_set)
            if not shared_attrs:
                continue

            shared_attrs_tuple = tuple(sorted(shared_attrs))
            pair = vo.Pair((left1, left2), shared_attrs_tuple)

            setJ = helper.intersectForObject(shared_attrs_tuple, bpcAttr)
            setM = helper.intersectForObject(shared_attrs_tuple, bpcAttrC)

            if setJ.getR() != 0 and setM.getR() != 0:
                setJ_right = _cached_tuple_set(setJ.getR(), tuple_set_cache)
                setM_right = _cached_tuple_set(setM.getR(), tuple_set_cache)
                if left1_set < setJ_right or left2_set < setM_right:
                    RAE.add(pair)

            AEC.add(pair)

    AEC.add(vo.Pair((tuple(), tuple()), tuple(attr)))
    AEC.add(vo.Pair((tuple(obj), tuple(obj)), tuple()))
    return AEC - RAE

def _compute_oe(bp1_views, bp2_views, bpcObj, bpcObjC, helper, obj, attr):
    OEC = set()
    ROE = set()
    tuple_set_cache = {}

    for _, right1, left1_set, right1_set in bp1_views:
        for _, right2, left2_set, right2_set in bp2_views:
            shared_objects = left1_set.intersection(left2_set)
            if not shared_objects:
                continue

            shared_objects_tuple = tuple(sorted(shared_objects))
            pair = vo.Pair(shared_objects_tuple, (right1, right2))

            setJ = helper.intersectForObject(shared_objects_tuple, bpcObj)
            setM = helper.intersectForObject(shared_objects_tuple, bpcObjC)

            if setJ.getR() != 0 and setM.getR() != 0:
                setJ_right = _cached_tuple_set(setJ.getR(), tuple_set_cache)
                setM_right = _cached_tuple_set(setM.getR(), tuple_set_cache)
                if right1_set < setJ_right or right2_set < setM_right:
                    ROE.add(pair)

            OEC.add(pair)

    OEC.add(vo.Pair(tuple(obj), (tuple(), tuple())))
    OEC.add(vo.Pair(tuple(), (tuple(attr), tuple(attr))))
    return OEC - ROE

def process_formal_context(input_file, output_file):
    """
    处理单个形式背景文件，生成三支概念
    """
    print(f"\n处理文件: {input_file}")
    print(f"输出文件: {output_file}")
    
    cur1 = dt.datetime.now()
    
    # 加载形式背景
    adjMat, adjMatC, obj, attr = load_formal_context(input_file)
    helper = bs.BasicCL()
    
    # 计算原形式背景和补形式背景下的概念格cl,clC
    cl = CL.cl(adjMat, obj, attr, helper=helper)
    clC = CL.cl(adjMatC, obj, attr, helper=helper)

    bp1 = cl.__getitem__(2)
    bp2 = clC.__getitem__(2)

    bpcObj = cl.__getitem__(3)
    bpcObjC = clC.__getitem__(3)

    bpcAttr = cl.__getitem__(4)
    bpcAttrC = clC.__getitem__(4)

    bp1_views = _prepare_concept_views(bp1)
    bp2_views = _prepare_concept_views(bp2)

    AE = _compute_ae(bp1_views, bp2_views, bpcAttr, bpcAttrC, helper, obj, attr)
    OE = _compute_oe(bp1_views, bp2_views, bpcObj, bpcObjC, helper, obj, attr)

    cur2 = dt.datetime.now()
    time = cur2 - cur1
    print(f"处理用时: {time}")

    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # 保存结果到文件
    with open(output_file, 'w', encoding='utf-8') as fi:
        fi.write("用时：" + str(time) + "\n")
        fi.write("len(OE):" + str(len(OE)) + ",len(AE)" + str(len(AE)) + "\n\n")
        fi.write("OE:\n")
        for i in OE:
            fi.write(str(i.getL()) + "#" + str(i.getR()) + "\n")

        fi.write("AE:\n")
        for i in AE:
            fi.write(str(i.getL()) + "#" + str(i.getR()) + "\n")

    print(f"结果已保存到: {output_file}")
    print(f"OE概念数量: {len(OE)}, AE概念数量: {len(AE)}")
    
    return len(OE), len(AE)

def threeWcl():
    """
    主函数：自动处理条件和决策形式背景文件，生成三支概念
    """
    print("="*60)
    print("三支概念格自动生成程序")
    print("="*60)
    
    # 定义输入和输出文件路径为当前项目根目录
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    # 输入文件路径
    condition_input = os.path.join(base_path, "test_contexts", "decision_formal_context_condition.txt")
    decision_input = os.path.join(base_path, "test_contexts", "decision_formal_context_decision.txt")
    
    # 输出文件路径
    condition_output = os.path.join(base_path, "test_results", "threeWcl_condition.txt")
    decision_output = os.path.join(base_path, "test_results", "threeWcl_decision.txt")

    # 检查输入文件是否存在
    if not os.path.exists(condition_input):
        print(f"错误：找不到条件形式背景文件: {condition_input}")
        return
    
    if not os.path.exists(decision_input):
        print(f"错误：找不到决策形式背景文件: {decision_input}")
        return
    
    print("输入文件:")
    print(f"  条件形式背景: {condition_input}")
    print(f"  决策形式背景: {decision_input}")
    print("\n输出文件:")
    print(f"  条件三支概念: {condition_output}")
    print(f"  决策三支概念: {decision_output}")
    
    total_start = dt.datetime.now()
    
    # 处理条件形式背景
    print("\n" + "="*40)
    print("处理条件形式背景")
    print("="*40)
    condition_oe_count, condition_ae_count = process_formal_context(condition_input, condition_output)
    
    # 处理决策形式背景
    print("\n" + "="*40)
    print("处理决策形式背景")
    print("="*40)
    decision_oe_count, decision_ae_count = process_formal_context(decision_input, decision_output)
    
    total_end = dt.datetime.now()
    total_time = total_end - total_start
    
    # 输出汇总信息
    print("\n" + "="*60)
    print("处理完成！汇总信息")
    print("="*60)
    print(f"总用时: {total_time}")
    print(f"\n条件属性三支概念:")
    print(f"  OE概念数量: {condition_oe_count}")
    print(f"  AE概念数量: {condition_ae_count}")
    print(f"  输出文件: {condition_output}")
    
    print(f"\n决策属性三支概念:")
    print(f"  OE概念数量: {decision_oe_count}")
    print(f"  AE概念数量: {decision_ae_count}")
    print(f"  输出文件: {decision_output}")
    
    print(f"\n总计:")
    print(f"  OE概念: {condition_oe_count + decision_oe_count}")
    print(f"  AE概念: {condition_ae_count + decision_ae_count}")
    print("="*60)

if __name__ == "__main__":
    threeWcl()

