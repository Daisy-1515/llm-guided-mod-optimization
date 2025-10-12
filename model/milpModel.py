
"""
* File: milpModel.py
* Author: Yi
*
* created on 2024/07/29
"""
"""
@package milpModel.py
@brief This module handles basic optimization template.
"""
import gurobipy as gb
import time

"""
taxiInputs - list of class Taxi
passInputs - list of class Passenger

"""
class generalModel:
    """
    @class generalModel
    @brief Manages basic optimization template.
    """
    def __init__(self, DistMatrix, wpList, taxiList):
        self.distMatrix = DistMatrix # { o: {d: float(row[d])/60.0 for d in wpList} for o, row in DistMatrix.items()} 
        self.wpList = wpList.copy()
        self.taxiList = taxiList.copy()
        self.taxi = None
        self.passenger = None
        self.wpNum = len(DistMatrix.keys())
        self.passNum = None
        self.model = None

        self.epsilon = 0.02
        self.M = 100000
        self.gap = 0.05

    def solveProblem(self):

        self.initModel()
        self.setupVars()
        self.setupCons()
        self.setupObj()

        print("*****************Start Optimize************")

        #self.model.Params.MIPGap = self.gap
        #self.model.setParam('MIPFocus', 2)
        # self.model.Params.Presolve = 1
        # self.model.setParam('Threads', 32)
        # self.model.setParam('NodeLimit', 5000)

        starttime = time.time()
        self.model.optimize()
        endtime = time.time()

        print("*****************RUN TIME************")
        print(endtime - starttime)

        if(self.model.status == gb.GRB.INFEASIBLE):
            self.model.computeIIS()
            self.model.write("model.ilp")
            return False, -1

        obj = self.model.objVal
        print("*****************OBJ COST************")
        print(obj)

        # Print solution
        if self.model.status == gb.GRB.Status.OPTIMAL:
            return True, obj
        
        return False, obj

    def initModel(self):
        pass

    def setupVars(self):
        pass

    def setupCons(self):
        pass

    def setupObj(self):
        pass



                

            


                
