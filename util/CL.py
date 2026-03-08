#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Author  : yixuan yang
# @File    : CL.py

import util.basic as basic
import util.vo as vo

#if __name__ == "__main__":
def cl(adjMat, obj, attr):

        numObj = len(obj)
        numAttr = len(attr)

        bpcObj = basic.BasicCL().getBPCliqueObj(adjMat,obj,attr,numObj,numAttr)
        bpcAttr = basic.BasicCL().getBPCliqueAttr(adjMat,obj,attr,numObj,numAttr)

        objResult = basic.BasicCL().objRes(obj,attr,bpcObj,bpcAttr)

        bp =  basic.BasicCL().finalBpcAll(objResult,bpcObj, bpcAttr)

        bpCliques = bp.__getitem__(0)

        attrResult = bp.__getitem__(1)


        unspcBpcliques = bpCliques.copy()

        spcObj = []
        for i in range(len(obj)):
            spcObj.append(obj.__getitem__(i))
        spcAttr = []
        for i in range(len(attr)):
            spcAttr.append(attr.__getitem__(i))
        spcObj = tuple(spcObj)
        spcAttr = tuple(spcAttr)

        spcC1 = vo.Pair(spcObj,())
        spcC2 = vo.Pair((),spcAttr)
        bpCliques.append(spcC1)
        bpCliques.append(spcC2)

        objResult.add(spcObj)
        objResult.add(tuple())

        attrResult.add(spcAttr)
        attrResult.add(tuple())


        #for temp in bpCliques:
            #print(temp.getL(),"#",temp.getR())


        #print(objResult)
        return objResult, attrResult, bpCliques, bpcObj, bpcAttr



