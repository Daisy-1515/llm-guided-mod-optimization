import gurobipy as gb
from dataclasses import dataclass

@dataclass
class Taxi:
    def __init__(self, start_pos: int, arrival_time: int, index:int):
        self.start_pos = start_pos  # same index in distMatrix
        self.arrival_time = arrival_time  # absolute time
        self.index = index
@dataclass
class Passenger:
    def __init__(self, start: int, end: int, ocurr:int, index:int):
        self.origin = start      # same index in distMatrix
        self.destination = end   # same index in distMatrix
        self.arrTime = ocurr
        self.index = index
        
class assignmentModel:
    """
    @class assignmentModel
    @brief Manages the first-level optimization problem.
    """
    def __init__(self, distMatrix, dynamic_obj_func=None):
        self.distMatrix = distMatrix
        self.dynamic_obj_func = dynamic_obj_func
        
        if self.dynamic_obj_func:
            exec(self.dynamic_obj_func, globals(), locals())
            self.dynamic_obj_func = locals().get("dynamic_obj_func", None)
    
    def updateInputs(self, taxiInputs, passengerInputs):
        self.taxi = taxiInputs   # a dictionary with key as taxi index, element as an instance of Taxi class 
        self.passenger = passengerInputs # a dictionary with key as passenger index, element as an instance of Passenger class 
        
    def initModel(self):
        self.model = gb.Model("Taxi Assignment optimization problem !")
        
    def setupVars(self):
        self.y = {}
        for v in self.taxi.keys(): 
            for p in self.passenger.keys():
                self.y[v,p] = self.model.addVar(vtype=gb.GRB.BINARY, lb=0, name="Y_%d_%d"%(v,p))
        self.model.update()

    def setupCons(self):
        self.model.addConstrs((gb.quicksum(self.y[v, p] for v in self.taxi.keys()) == 1 for p in self.passenger.keys()))
        
    def setupObj(self):
        if self.dynamic_obj_func:
            self.dynamic_obj_func(self) # Call the dynamic function if it exists
        else:
            print("No dynamic_obj_func found. Using default.")
            self.default_dynamic_obj_func()
            
            
    def dynamic_obj_func(self):
        print("Creating dynamic objectives for Assignment Model")
        
        # Cost component 1: Passenger waiting time from request to taxi arrival
        cost1 = gb.quicksum(
            self.y[v, p] * max(self.taxi[v].arrival_time - self.passenger[p].arrTime, 0)
            for v in self.taxi.keys() for p in self.passenger.keys())
        
        # Cost component 2: Taxi detour time from current position to passenger pickup
        cost2 = gb.quicksum(
            self.y[v, p] * self.distMatrix[self.taxi[v].start_pos][self.passenger[p].origin]
            for v in self.taxi.keys() for p in self.passenger.keys())
        
        # Cost component 3: Passenger trip time from pickup to drop-off
        cost3 = gb.quicksum(
            self.y[v, p] * self.distMatrix[self.passenger[p].origin][self.passenger[p].destination]
            for v in self.taxi.keys() for p in self.passenger.keys())
        
        # Cost component 4: Penalty for multiple assignments per taxi
        cost4 = gb.quicksum(
            (gb.quicksum(self.y[v, p] for p in self.passenger.keys())) ** 2
            for v in self.taxi.keys())
        
        # Weights list for cost components
        weights = [1, 1, 1, 100]
        
        # Combine cost components
        costs = [cost1, cost2, cost3, cost4]
        
        # Build and set the objective
        objective = sum(w * c for w, c in zip(weights, costs))
        self.model.setObjective(objective, gb.GRB.MINIMIZE)

        
