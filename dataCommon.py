"""
* File: dataCommon.py
* Author: Yi
*
* created on 2024/08/19
"""
"""
@package dataCommon.py
@brief This module provide basic dataclass template.
"""
class Taxi:
    def __init__(self, start_pos: int, arrival_time: int, index:int):
        self.start_pos = start_pos
        self.arrival_time = arrival_time 
        self.index = index
    def __eq__(self, other):
        if not isinstance(other, Taxi):
            return False
        return (
            self.start_pos == other.start_pos
            and self.arrival_time == other.arrival_time
            and self.index == other.index
        )
    def print(self):
        info = {"start_pos": self.start_pos, "arr": self.arrival_time, "taxi_id": self.index}
        print(info)


class Passenger:
    def __init__(self, start: int, end: int, ocurr:int, index:int):
        self.origin = start
        self.destination = end
        self.arrTime = ocurr
        self.index = index
    def __eq__(self, other):
        if not isinstance(other, Passenger):
            return False
        return (
            self.origin == other.origin
            and self.destination == other.destination
            and self.arrTime == other.arrTime
            and self.index == other.index
        )
    def print(self):
        info = {"o":self.origin, "d":self.destination, "arr":self.arrTime, "passenger_id":self.index}
        print(info)

class Task:
    def __init__(self, start: int, end: int, index:int, ocurr:int, vehArr:int, vehDep:int):
        self.origin = start
        self.destination = end
        self.pedArr = ocurr
        self.pedIndex = index
        self.vehArrOrigin = vehArr
        self.vehDepOrigin = vehDep
        self.archive_time = -1
        self.assign_time = -1
    def print(self):
        info = {"o":self.origin, "d":self.destination, "pedArr":self.pedArr, "pedIndex":self.pedIndex, "vArr":self.vehArrOrigin, "vDep":self.vehDepOrigin, "archive_time":self.archive_time, "assign_time":self.assign_time}
        print(info)

        