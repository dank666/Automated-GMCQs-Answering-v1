#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Author  : yixuan yang
# @File    : th_wcl.py

import util.vo as vo
import util.basic as bs

def th_wcl(obj, attr, bp1, bp2, bpcAttr, bpcAttrC, bpcObj, bpcObjC):  # bp1是原背景概念格，bp2是补背景概念格
    AEC = set()  # 属性外延候选集
    OEC = set()  # 对象外延候选集

    RAE = set()  # 需要排除的属性外延集
    ROE = set()  # 需要排除的对象外延集

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

    # for i in bp1:
    #     for j in bp2:
    #         set1 = set(i.getL())
    #         set2 = set(j.getL())
    #         setT = set1.intersection(set2)
    #         if len(setT) == 0:
    #             pass
    #         else:
    #             tt = []
    #             tt.append(i.getR())
    #             tt.append(j.getR())
    #             p = vo.Pair(tuple(setT),tuple(tt))
    #             OEC.add(p)

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

    return OE, AE