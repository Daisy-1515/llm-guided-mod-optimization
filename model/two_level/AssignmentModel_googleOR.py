from ortools.linear_solver import pywraplp
from ortools.sat.python import cp_model
from dataclasses import dataclass
from model.milpModel import generalModel
from legacy_mod.dataCommon import Task, Taxi, Passenger

class assignmentModel(generalModel):
    def __init__(self, DistMatrix, wpList, taxiList, dynamic_obj_func=None):
        super().__init__(DistMatrix, wpList, taxiList)
        self.distMatrix = DistMatrix
        self.dynamic_obj_func = dynamic_obj_func
        self.status = None
        
        if self.dynamic_obj_func:
            exec(self.dynamic_obj_func, globals(), locals())
            self.dynamic_obj_func = locals().get("dynamic_obj_func", None)
    
    def updateInputs(self, taxiInputs, passengerInputs):
        self.status = None
        self.taxi = taxiInputs   # Dictionary with key as taxi index, value as Taxi instance
        self.passenger = passengerInputs  # Dictionary with key as passenger index, value as Passenger instance
    
    def initModel(self):
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
    
    def setupVars(self):
        self.y = {}
        for v in self.taxi.keys(): 
            for p in self.passenger.keys():
                self.y[v, p] = self.model.NewBoolVar(f"Y_{v}_{p}")
    
    def setupCons(self):
        # Each passenger is assigned to exactly one taxi
        for p in self.passenger.keys():
            self.model.Add(sum(self.y[v, p] for v in self.taxi.keys()) == 1)
    
    def setupObj(self):
        if self.dynamic_obj_func:
            self.dynamic_obj_func(self)  # Call the dynamic function if it exists
        else:
            print("No dynamic_obj_func found. Using default.")
            self.default_dynamic_obj_func()
    
    def default_dynamic_obj_func(self):
        weights = [1, 1, 1, 100]  # Weights for each cost
        objective = 0
        
        # Cost 1: Distance from taxi start position to passenger's origin
        for v in self.taxi.keys():
            for p in self.passenger.keys():
                objective += weights[0] * self.distMatrix[self.taxi[v].start_pos][self.passenger[p].origin] * self.y[v, p]

        # Cost 2: Distance from taxi start position to passenger's destination
        for v in self.taxi.keys():
            for p in self.passenger.keys():
                objective += weights[1] * self.distMatrix[self.taxi[v].start_pos][self.passenger[p].destination] * self.y[v, p]

        # Cost 3: Time delay (arrival time - passenger's arrival time)
        for v in self.taxi.keys():
            for p in self.passenger.keys():
                objective += weights[2] * max(self.taxi[v].arrival_time - self.passenger[p].arrTime, 0) * self.y[v, p]

        # # Cost 4: Quadratic cost term for each taxi (summation of squared decision variables)
        for v in self.taxi.keys():
            sum_y = self.model.NewIntVar(0, len(self.passenger), f"sum_y_{v}")  # Auxiliary sum variable
            self.model.Add(sum_y == sum(self.y[v, p] for p in self.passenger.keys()))

            sum_y_squared = self.model.NewIntVar(0, len(self.passenger) ** 2, f"sum_y_squared_{v}")  # Squared term
            self.model.AddMultiplicationEquality(sum_y_squared, sum_y, sum_y)

            objective += weights[3] * sum_y_squared
            # Set the objective to minimize
            self.model.Minimize(objective)
        
    def solveProblem(self):
        # Initialize the solver, variables, constraints, and objective function
        self.initModel()
        self.setupVars()
        self.setupCons()
        self.setupObj()

        print("*****************Start Optimize************")
    
        # Solve the problem using CpSolver
        status = self.solver.Solve(self.model)
        self.status = status

        # Check the solver status and handle different outcomes
        if status == cp_model.OPTIMAL:
            obj = self.solver.ObjectiveValue()
            print("*****************OBJ COST************")
            print(obj)
            return True, obj
        
        elif status == cp_model.FEASIBLE:
            obj = self.solver.ObjectiveValue()
            print("Solution is feasible but not optimal:")
            print(obj)
            return False, obj
        
        else:
            print("No solution found.")
            return False, -1
        
    def getOutputs(self):
        vehResult = {}
        
        # Check if the solver found an optimal or feasible solution
        if self.status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            # Iterate over each taxi
            for v in self.taxi.keys():
                vehTask = []
                # Iterate over each passenger and check if the corresponding y[v, p] variable is 1
                for p in self.passenger.keys():
                    if self.solver.Value(self.y[v, p]) > 0.5:  # If the decision variable is 1 (assignment)
                        vehTask.append(p)
                
                if len(vehTask) > 0:
                    vehResult[self.taxi[v].index] = vehTask
                else:
                    vehResult[self.taxi[v].index] = []  # No passengers assigned
        
        else:
            print("Model Status is weird!")
        
        return vehResult
    
