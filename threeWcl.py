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

def process_formal_context(input_file, output_file):
    """
    处理单个形式背景文件，生成三支概念
    """
    print(f"\n处理文件: {input_file}")
    print(f"输出文件: {output_file}")
    
    cur1 = dt.datetime.now()
    
    # 加载形式背景
    adjMat, adjMatC, obj, attr = load_formal_context(input_file)
    
    # 计算原形式背景和补形式背景下的概念格cl,clC
    cl = CL.cl(adjMat, obj, attr)
    clC = CL.cl(adjMatC, obj, attr)

    bp1 = cl.__getitem__(2)
    bp2 = clC.__getitem__(2)

    bpcObj = cl.__getitem__(3)
    bpcObjC = clC.__getitem__(3)

    bpcAttr = cl.__getitem__(4)
    bpcAttrC = clC.__getitem__(4)

    AEC = set()
    OEC = set()

    RAE = set()
    ROE = set()

    # 计算AE，i.getL()是A1, j.getR()是A2,i.getR()是B1，j.getR()是B2
    for i in bp1:
        for j in bp2:
            set1 = set(i.getR())
            set2 = set(j.getR())
            # setT = set1.intersection(set2)
            setT = set2.intersection(set1)
            if len(setT) == 0:
                pass
            else:
                tt = []
                tt.append(i.getL())
                tt.append(j.getL())
                p = vo.Pair(tuple(tt), tuple(setT))
                # if set(i.getL()).issubset(setT):
                #     RAE.add(p)
                # print("setT:",setT)
                setJ = bs.BasicCL().intersectForObject(setT, bpcAttr)  # setJ是原背景下B1交B2 的集合作下运算得到的pair（内涵，外延）
                setM = bs.BasicCL().intersectForObject(setT, bpcAttrC)
                # print("setJ:", setJ.getR(), "#", setJ.getL())
                # print("setM:", setM.getR(), "#", setM.getL())

                if setJ.getR() == 0 or setM.getR() == 0:
                    pass
                else:

                    if set(i.getL()) < set(setJ.getR()) or set(j.getL()) < set(setM.getR()):
                        # print(p.getL(),"#", p.getR())
                        RAE.add(p)
                        # A1属于B1交B2 的子集 or A2 属于B1交B2 补背景的 外延子集

                AEC.add(p)

    # 添加特殊顶部和底部两个三支概念
    spcTop = vo.Pair(tuple([tuple(), tuple()]), tuple(attr))
    spcButtom = vo.Pair(tuple([tuple(obj), tuple(obj)]), tuple([]))
    # print(spcTop.getL(), spcTop.getR())
    AEC.add(spcTop)
    AEC.add(spcButtom)
    AE = AEC - RAE

    # 计算OE
    for i in bp1:
        for j in bp2:
            set1 = set(i.getL())
            set2 = set(j.getL())
            setT = set1.intersection(set2)
            if len(setT) == 0:
                pass
            else:
                tt = []
                tt.append(i.getR())
                tt.append(j.getR())
                p = vo.Pair(tuple(setT), tuple(tt))
                # if set(i.getL()).issubset(setT):
                #     RAE.add(p)
                # print("setT:",setT)
                setJ = bs.BasicCL().intersectForObject(setT, bpcObj)  # setJ是原背景下A1交A2 的集合作下运算得到的pair（外延，内涵）
                setM = bs.BasicCL().intersectForObject(setT, bpcObjC)
                # print("setJ:", setJ.getR(), "#", setJ.getL())
                # print("setM:", setM.getR(), "#", setM.getL())

                if setJ.getR() == 0 or setM.getR() == 0:
                    pass
                else:

                    if set(i.getR()) < set(setJ.getR()) or set(j.getR()) < set(setM.getR()):
                        # print(p.getL(),"#", p.getR())
                        ROE.add(p)
                        # A1属于B1交B2 的子集 or A2 属于B1交B2 补背景的 外延子集

                OEC.add(p)
    spcTop = vo.Pair(tuple(obj), tuple([tuple(), tuple()]))
    spcButtom = vo.Pair(tuple([]), tuple([tuple(attr), tuple(attr)]))
    OEC.add(spcTop)
    OEC.add(spcButtom)
    OE = OEC - ROE

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


