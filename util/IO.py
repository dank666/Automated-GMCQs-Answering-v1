#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Author  : yixuan yang
# @File    : IO.py

import numpy as np

# 读取和预处理形式概念分析所需的形式背景数据
def io():



    #读入形式背景
    filename = input("请输入文件名：")
    # filename = '/Users/yxyang/Desktop/t7.txt'

    with open(filename, "r") as f:
        numObj = int(f.readline())#获取对象数量
        numAttr = int(f.readline())#获取属性数量
        adjMat = np.zeros(shape=(numObj, numAttr), dtype=int)#存储形式背景矩阵
        adjMatC = np.zeros(shape=(numObj, numAttr), dtype=int)  # 存储补形式背景矩阵
        obj = []
        attr = []

        #将形式背景存储到矩阵内
        for i in range(numObj):
            obj.append(i+1)
            for j in range(numAttr):
                t = int(f.read(1))
                adjMat[i][j] = t
                adjMatC[i][j] =  1 if t == 0 else 0 # 0 和 1 背景取反
            f.read(1)  # 读取行末的换行符

        for i in range(numAttr):
            attr.append(i+1)

        # print("原背景：")
        # print(adjMat)
        # print("补背景：")
        # print(adjMatC)

        # adjMat是原背景矩阵，adjMatC是补背景矩阵，obj是对象集，attr是属性集
        return adjMat, adjMatC, obj, attr



