"""
* File: SequencingModel.py
* Author: Yi
*
* created on 2025/01/22
"""
"""
@package SequencingModel.py
@brief This module handles the second-level optimization problem.

@dependencies
- model.milpModel
- dataCommon
"""
import itertools
import gurobipy as gb
from model.milpModel import generalModel
from legacy_mod.dataCommon import Task

class sequencingModel(generalModel):
    """
    @class sequencingModel
    @brief Manages the second-level optimization model.
    """
    def __init__(self, DistMatrix, wpList, taxiList):
        super().__init__(DistMatrix, wpList, taxiList)
        self.vehIdx = None
        self.vehLoc = None
        self.seqPassList = None
        self.seqPassNum = None
        self.maxPassIdx = None
        self.extendList = None
        self.ar = {}
        self.dp = {}
        self.wt = {}
        self.x = {}
        self.unit = 1.0
    
    def updateInputs(self,  vehIndex, specificTaxi, assignedPassList, passengerInfo):
        self.vehIdx = vehIndex
        self.targetTaxi = specificTaxi
        self.targetTaxi.arrival_time /= self.unit
        self.seqPassList = assignedPassList.copy()
        self.passenger = passengerInfo.copy()
        self.seqPassNum = len(assignedPassList)
        self.maxPassIdx = max(assignedPassList)
        self.vehLoc = specificTaxi.start_pos
        
    def initModel(self):
        self.model = gb.Model("Taxi Sequencing optimization problem !")
        self.model.setParam('TimeLimit', 5)
        #self.model.setParam('OutputFlag',0)
        
    def setupVars(self):
        print ("Create Variables for Sequencing Model!")
        
        self.extendList = self.seqPassList.copy()
        self.extendList.append(self.maxPassIdx+1) # car start location
        self.extendList.append(self.maxPassIdx+2) # virtual car end location (same as last passenger drop off location)
        # define variables
        for p in self.extendList: 
            self.ar[p] = self.model.addVar(vtype=gb.GRB.CONTINUOUS, lb=0, name="AR_%d"%(p))
            self.dp[p] = self.model.addVar(vtype=gb.GRB.CONTINUOUS, lb=0, name="DP_%d"%(p))
            for p2 in self.extendList:
                self.x[p,p2] = self.model.addVar(vtype=gb.GRB.BINARY, lb=0, name="X_%d_%d"%(p,p2))
            self.wt[p] = self.model.addVar(vtype=gb.GRB.CONTINUOUS, lb=0, name="WT_%d"%(p))

        self.model.update()

    def setupCons(self):
        print ("Create Constraints for Sequencing Model!")
        startSet = self.seqPassList.copy()
        startSet.append(self.maxPassIdx+1)
        endSet = self.seqPassList.copy()
        endSet.append(self.maxPassIdx+2)
        
        # define constraints
        ############################## Initial taxi location and time assignment ###################################

        # start location assignment
        self.model.addConstr((gb.quicksum(self.x[p, self.maxPassIdx+1] for p in self.seqPassList) == 0))
        self.model.addConstr((gb.quicksum(self.x[self.maxPassIdx+1, p] for p in self.seqPassList) <= 1))

        # arrival time at start location
        self.model.addConstr((self.ar[self.maxPassIdx+1] == (self.targetTaxi.arrival_time) ))
        self.model.addConstr((self.dp[self.maxPassIdx+1] == (self.targetTaxi.arrival_time) ))
        
        # final location assignment
        self.model.addConstr((gb.quicksum(self.x[self.maxPassIdx+2, p] for p in self.seqPassList) == 0))
        self.model.addConstr((gb.quicksum(self.x[p, self.maxPassIdx+2] for p in self.seqPassList) <= 1))
        
        # departure time at final location
        self.model.addConstr((self.dp[self.maxPassIdx+2] == self.ar[self.maxPassIdx+2]))
        
        ############################## Passenger convervation law Constraints ###################################
        self.model.addConstrs( (gb.quicksum(self.x[i, p] for i in startSet) == gb.quicksum(self.x[p, j] for j in endSet) for p in self.seqPassList) )
        
        self.model.addConstrs((self.x[p, p] == 0 for p in self.seqPassList))
        self.model.addConstrs( ((gb.quicksum(self.x[i, p] for i in startSet) == 1) for p in self.seqPassList) )
        
        ############################## Arrival Departure Dynamic Constraints ###################################
        
        # start position
        self.model.addConstrs((self.ar[p] - self.dp[self.maxPassIdx+1] - self.distMatrix[self.vehLoc][self.passenger[p].origin] <= 
                               self.M * (1 - self.x[self.maxPassIdx+1, p])
                               for p in self.seqPassList))
        self.model.addConstrs((self.ar[p] - self.dp[self.maxPassIdx+1] - self.distMatrix[self.vehLoc][self.passenger[p].origin] >= 
                               -self.M * (1 - self.x[self.maxPassIdx+1, p]) 
                               for p in self.seqPassList))
        
        # passenger chain
        self.model.addConstrs((self.ar[p2] - self.dp[p1] - self.distMatrix[self.passenger[p1].origin][self.passenger[p1].destination]
                               - self.distMatrix[self.passenger[p1].destination][self.passenger[p2].origin] <= 
                               self.M * (1 - self.x[p1, p2]) 
                               for p1 in self.seqPassList for p2 in self.seqPassList))
        self.model.addConstrs((self.ar[p2] - self.dp[p1] - self.distMatrix[self.passenger[p1].origin][self.passenger[p1].destination] 
                               - self.distMatrix[self.passenger[p1].destination][self.passenger[p2].origin] >= 
                               -self.M * (1 - self.x[p1, p2]) 
                               for p1 in self.seqPassList for p2 in self.seqPassList))
        
        # end position
        self.model.addConstrs((self.ar[self.maxPassIdx+2] - self.dp[p] - self.distMatrix[self.passenger[p].origin][self.passenger[p].destination] 
                               - 0 <= 
                               self.M * (1 - self.x[p, self.maxPassIdx+2]) 
                               for p in self.seqPassList ))
        self.model.addConstrs((self.ar[self.maxPassIdx+2] - self.dp[p] - self.distMatrix[self.passenger[p].origin][self.passenger[p].destination] 
                               - 0 >= 
                               -self.M * (1 - self.x[p, self.maxPassIdx+2]) 
                               for p in self.seqPassList ))
        
        self.model.addConstrs((self.dp[p] >= (self.passenger[p].arrTime/ self.unit) for p in self.seqPassList) )
        self.model.addConstrs((self.dp[p] >= self.ar[p] for p in self.seqPassList) )
        
        print('###finish read in constraints####')
        # Save model
        self.model.write('./model/model_formulation/MatchModel_for_taxi'+str(self.vehIdx)+'.lp')
        print('####################')
        print(self.model.NumVars)
        print(self.model.NumConstrs)
        print('####################')
        
    def setupObj(self):
        print ("Create objectives for Sequencing Model!")
        
        # passenger waiting time cost
        for p in self.seqPassList:
            self.model.addConstr(self.wt[p] == (self.dp[p]- (self.passenger[p].arrTime/self.unit) ) )

        passCost = gb.quicksum(self.wt[p] for p in self.seqPassList )

        self.model.setObjective(passCost, gb.GRB.MINIMIZE)  


    def getOutputs(self):
        vehTask = []
        
        if self.model.status not in (gb.GRB.INFEASIBLE, gb.GRB.UNBOUNDED):
            Ar = self.model.getAttr('x', self.ar)
            dp = self.model.getAttr('x', self.dp)
            
            for p in self.seqPassList:
                origin = self.passenger[p].origin
                dest = self.passenger[p].destination
                index = self.passenger[p].index
                ocurr = self.passenger[p].arrTime
                arrTime = Ar.get((p))
                depTime = dp.get((p))
                
                pedTask = Task(start=origin, end=dest, index=index, ocurr=ocurr, vehArr = int(arrTime*self.unit), vehDep = int(depTime*self.unit))
                vehTask.append(pedTask)
                        
                vehTask.sort(key=lambda ped: ped.vehArrOrigin)
        else:
            print("Model Status weird !!!")
        
        return vehTask

class sequencingKOpt:
    """
    @class sequencingKOpt
    @brief Manages the second-level optimization problem when scale is large.
    """
    def __init__(self, DistMatrix):
        self.distMatrix = DistMatrix.copy()

        self.vehIdx = None
        self.vehLoc = None
        self.seqPassList = None
        self.seqPassNum = None
        self.targetTaxi = None

    def updateInputs(self, vehIndex, specificTaxi, assignedPassList, passengerInfo):
        self.vehIdx = vehIndex
        self.targetTaxi = specificTaxi
        self.seqPassList = assignedPassList.copy()
        self.passenger = passengerInfo.copy()
        self.seqPassNum = len(assignedPassList)
        self.vehLoc = specificTaxi.start_pos

    def calculate_wait_time(self, route):
        """Calculates the total waiting time for a given route."""
        taxi_time = self.targetTaxi.arrival_time
        total_waiting_time = 0

        for p in route:
            passenger = self.passenger[p]

            # Arrival time at passenger's pickup location
            taxi_time += self.distMatrix[self.vehLoc][passenger.origin]
            wait_time = max(0, taxi_time - passenger.arrTime)
            total_waiting_time += wait_time

            # Update location and time
            taxi_time += self.distMatrix[passenger.origin][passenger.destination]
            self.vehLoc = passenger.destination

        return total_waiting_time

    def solveProblem(self):
        """Performs a k-opt optimization (2-opt by default) to minimize passenger waiting time."""
        best_route = self.seqPassList[:]
        best_wait_time = self.calculate_wait_time(best_route)

        improved = True

        while improved:
            improved = False

            for i, j in itertools.combinations(self.seqPassList, 2):
                # Find their positions in the current route
                pos_i = best_route.index(i)
                pos_j = best_route.index(j)

                # Ensure pos_i < pos_j for slicing
                if pos_i > pos_j:
                    pos_i, pos_j = pos_j, pos_i

                # Perform the 2-opt swap
                new_route = best_route[:pos_i] + best_route[pos_i:pos_j + 1][::-1] + best_route[pos_j + 1:]
                new_wait_time = self.calculate_wait_time(new_route)

                if new_wait_time < best_wait_time:
                    best_route = new_route
                    best_wait_time = new_wait_time
                    improved = True

        self.seqPassList = best_route
        return best_wait_time

    def getOutputs(self):
        vehTask = []
        visitSolution = {}

        taxi_time = self.targetTaxi.arrival_time
        current_loc = self.targetTaxi.start_pos

        for p in self.seqPassList:
            passenger = self.passenger[p]

            # Arrival time at pickup
            taxi_time += self.distMatrix[current_loc][passenger.origin]
            arrival_time = taxi_time

            # Departure time from pickup
            departure_time = max(arrival_time, passenger.arrTime)
            if p != self.seqPassList[-1]:
                taxi_time = departure_time + self.distMatrix[passenger.origin][passenger.destination]

            visitSolution[p] = [arrival_time, departure_time]
            current_loc = passenger.destination

        for p, sol in visitSolution.items():
            origin = self.passenger[p].origin
            dest = self.passenger[p].destination
            index = self.passenger[p].index
            ocurr = self.passenger[p].arrTime
            arrTime = sol[0]
            depTime = sol[1]

            pedTask = Task(start=origin, end=dest, index=index, ocurr=ocurr, vehArr=arrTime, vehDep=depTime)
            vehTask.append(pedTask)

        vehTask.sort(key=lambda ped: ped.vehArrOrigin)

        return vehTask
