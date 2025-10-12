"""
* File: assignmentModel.py
* Author: Yi
*
* created on 2025/01/21
"""
"""
@package AssignmentModel.py
@brief This module handles the first-level optimizaton model.

@dependencies
- model.milpModel
- dataCommon
"""

import gurobipy as gb
from model.milpModel import generalModel
from dataCommon import Task

class assignmentModel(generalModel):
    """
    @class assignmentModel
    @brief Manages the first-level optimization problem.
    """
    def __init__(self, DistMatrix, wpList, taxiList, dynamic_obj_func=None, weightsObj = None):
        super().__init__(DistMatrix, wpList, taxiList)
        self.error_message = None
        self.string_func = dynamic_obj_func
        self.dynamic_obj_func = dynamic_obj_func
        self.weightForObj = weightsObj
        # If dynamic_obj_func is provided, assign it to the instance
        if isinstance(self.dynamic_obj_func, str):
            try:
                namespace = {}
                exec(self.dynamic_obj_func, globals(), namespace)
                self.dynamic_obj_func = namespace.get("dynamic_obj_func", None)
            except Exception as e:
                # Save the exception error message
                self.error_message = str(e) + ". ConversionError. As error there, I will use default obj."
                
                # Print the error message
                print(f"Error occurred during dynamic objective function setup: {self.error_message}")
                
                # Fallback to the default objective function in case of error
                print("Falling back to default objective function.")
                self.dynamic_obj_func = None
    
    def get_latest_func(self):
        return self.string_func
    
    def updateInputs(self, taxiInputs, passengerInputs):
        self.taxi = taxiInputs.copy()
        self.passenger = passengerInputs.copy()
        
    def initModel(self):
        self.model = gb.Model("Taxi Assignment optimization problem !")
        self.model.Params.MIPGap = self.gap
        self.model.setParam('TimeLimit', 10)
        #self.model.setParam('OutputFlag',0)
        
    def setupVars(self):
        print ("Create Variables for Assignment Model!")
        # define variables
        self.y = {}
        for v in self.taxiList: 
            for p in self.passenger.keys():
                self.y[v,p] = self.model.addVar(vtype=gb.GRB.BINARY, lb=0, name="Y_%d_%d"%(v,p))
        self.model.update()

    def setupCons(self):
        print ("Create Constraints for Assignment Model!")
        # define constraints
        ############################## Passenger assignment Constraints ###################################
        self.model.addConstrs((gb.quicksum(self.y[v, p] for v in self.taxiList) == 1 for p in self.passenger.keys()))
        
    def setupObj(self):
        
        if self.dynamic_obj_func == None:
            if self.string_func == None:
                print("No dynamic_obj_func found.")
                self.default_dynamic_obj_func()
                self.error_message = "None Obj. Error there, I will use default obj."
            else:
                self.default_dynamic_obj_func() # due to failed conversion from string to function
                
        else:
            try:
                self.dynamic_obj_func(self)  # Call the dynamic function if it exists
                self.error_message = "Your obj function is correct. Gurobi accepts your obj."
                self.latest_correct_func = self.string_func 
                    
            except Exception as e:
                # Save the exception error message
                self.error_message = str(e) + ". As error there, I will use default prompt obj for this iteration."
                
                # Print the error message
                print(f"Error occurred during dynamic objective function setup: {self.error_message}")
                
                # Fallback to the default objective function in case of error
                print("Falling back to default objective function.")
                self.default_dynamic_obj_func()

            
    def default_dynamic_obj_func(self):
        cost1 = gb.quicksum(gb.quicksum((self.distMatrix[self.taxi[v].start_pos][self.passenger[p].origin]*self.y[v,p]) for p in self.passenger.keys()) for v in self.taxi.keys()) 
        cost2 = gb.quicksum(gb.quicksum((self.distMatrix[self.taxi[v].start_pos][self.passenger[p].destination]*self.y[v,p]) for p in self.passenger.keys()) for v in self.taxi.keys()) 
        cost3 = gb.quicksum(gb.quicksum( (max(self.taxi[v].arrival_time - self.passenger[p].arrTime, 0)) * self.y[v, p] for p in self.passenger.keys())for v in self.taxi.keys())
        cost4 = gb.quicksum( gb.quicksum((self.y[v,p]) for p in self.passenger.keys())*gb.quicksum((self.y[v,p]) for p in self.passenger.keys()) for v in self.taxi.keys())
        
        costs = [cost1, cost2, cost3, cost4] # cost3
        
        # can also use self.taxi[v].arrival_time  and self.passenger[p].arrTime if needed
        if self.weightForObj != None:
            weights = [self.weightForObj[0], self.weightForObj[0], self.weightForObj[1], self.weightForObj[2]]
        else:
            weights = [1, 1, 1, 100]
        self.model.setObjective(gb.quicksum(w*c for w,c in zip(costs, weights)), gb.GRB.MINIMIZE)   

    def getOutputs(self):
        vehResult = {}
        
        if self.model.status not in (gb.GRB.INFEASIBLE, gb.GRB.UNBOUNDED):
            Y = self.model.getAttr('x', self.y)

            for v in self.taxiList:
                vehTask = []
                for p in self.passenger.keys():
                    if Y.get((v,p)) == 1:
                        vehTask.append(p)
                        
                if len(vehTask) >0:
                    vehResult[self.taxi[v].index] = vehTask
                else:
                    vehResult[self.taxi[v].index] = []      
        else:
            print("Model Status weird !!!")
        
        return vehResult
        
        
