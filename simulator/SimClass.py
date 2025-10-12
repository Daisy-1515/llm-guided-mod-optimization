"""
* File: SimClass.py
* Author: Yushen
*
* created on 2025/01/22
"""
"""
@package SimClass.py
@brief This module serves as an environment that evolve system dynamics.

@dependencies
- dataCommon
"""
import random
from dataCommon import *
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Dict
import pandas as pd

class SimEnvironment:
    def __init__(self, state_info: Dict[int, Taxi], distance_matrix):  # state_info[i]: taxi
        self.current_time = 0
        self.task_archive: Dict[int, list[Task]] = {}  # archive[taxi] = list(task1, task2, ...)
        self.state_info = state_info
        self.dist_mat = distance_matrix
        self.command: Dict[int, list[Task]] = {}  # command[taxi] = list(task1, task2, ...)
        self.task_arr_time: Dict[int, list[int]] = {}
        self.task_finish_time: Dict[int, list[int]] = {}
        self.taxi_key_loc: Dict[int, list[(int, int)]] = {}
        self.total_waiting_time = 0
        self.total_travel_time = 0
        self.total_idle_time = 0
        for key in self.state_info.keys():
            self.command[key] = []
            self.task_archive[key] = []
            self.task_arr_time[key] = []
            self.task_finish_time[key] = []
            self.taxi_key_loc[key] = []

    def archive_task(self, taxi_no: int, task:Task, time:int):
        if taxi_no in self.task_archive.keys():
            task.archive_time = time
            self.task_archive[taxi_no].append(task)
        else:
            self.task_archive[taxi_no] = []
            task.archive_time = time
            self.task_archive[taxi_no].append(task)
    
    def print_task(self, taxi_no:int):
        if taxi_no in self.task_archive.keys():
            for task in self.task_archive[taxi_no]:
                print([task.origin, task.destination, task.pedArr, task.pedIndex, task.vehArrOrigin, task.vehDepOrigin])
        else:
            print("this taxi "+ str(taxi_no)+" is not saved in archive!")
    
    def update_command(self, vehResult: Dict[int, list[Task]]):
        assert(len(self.state_info)==len(vehResult))
        for key in self.state_info.keys():
            taxi = self.state_info[key]
            if len(self.command[key]) == 0:
                self.command[key] = vehResult[key]
                if len(self.command[key]) > 0:  # receive new order
                    current_task = self.command[key][0]
                    current_task.assign_time = self.current_time
                    if taxi.start_pos == current_task.origin: 
                        if taxi.arrival_time <= current_task.vehArrOrigin:  # idle at task origin
                            self.taxi_key_loc[key].append((taxi.start_pos,taxi.arrival_time))
                            self.task_arr_time[key].append(taxi.arrival_time)
                            taxi.arrival_time = current_task.vehDepOrigin + self.dist_mat[current_task.origin][current_task.destination]
                            taxi.start_pos = current_task.destination
                    else:  
                        if taxi.arrival_time <= self.current_time:  # idle not at origin
                            self.taxi_key_loc[key].append((taxi.start_pos,taxi.arrival_time))
                            self.task_arr_time[key].append(taxi.arrival_time)
                            taxi.arrival_time = self.current_time + self.dist_mat[taxi.start_pos][current_task.origin]
                            taxi.start_pos = current_task.origin
                        else:  # heading to somewhere
                            taxi.arrival_time += self.dist_mat[taxi.start_pos][current_task.origin]
                            taxi.start_pos = current_task.origin

            else:
                current_task = self.command[key][0]
                self.command[key] = [current_task] + vehResult[key]
                # if taxi.start_pos == current_task.origin:  # on the way to current task; current task can be reassigned
                #     self.command[key] = vehResult[key]
                # else:
                #     if taxi.start_pos == current_task.destination:  # already picked passenger, keep current task
                #         self.command[key] = [current_task] + vehResult[key]
                #     else:
                #         raise Exception("mismatched taxi position")

    def sim_one_step(self):
        self.current_time += 1
        for i in self.state_info.keys():
            taxi = self.state_info[i]
            if len(self.command[i]) > 0:  # it has task
                self.total_travel_time += 1
                current_task = self.command[i][0]
                if taxi.arrival_time <= self.current_time: 
                    if taxi.start_pos == current_task.origin:  # arrive at task origin, update start pos as destination and arrival time as dep time + travel time
                        self.taxi_key_loc[i].append((taxi.start_pos,self.current_time-(taxi.arrival_time<self.current_time)))
                        self.task_arr_time[i].append(taxi.arrival_time)
                        taxi.start_pos = current_task.destination
                        taxi.arrival_time = current_task.vehDepOrigin + self.dist_mat[current_task.origin][current_task.destination]
                    else:
                        if taxi.start_pos == current_task.destination:  # arrive at task destination, archive current task and remove from task list
                            self.taxi_key_loc[i].append((taxi.start_pos,self.current_time-(taxi.arrival_time<self.current_time)))
                            self.archive_task(taxi.index, current_task, self.current_time)
                            self.task_finish_time[i].append(taxi.arrival_time)
                            self.command[i].pop(0)
                            if len(self.command[i])>0:   # there is next task
                                current_task = self.command[i][0]
                                current_task.assign_time = self.current_time
                                if taxi.start_pos == current_task.origin:  # next task origin is current pos
                                    self.task_arr_time[i].append(taxi.arrival_time)
                                    taxi.arrival_time = current_task.vehDepOrigin + self.dist_mat[taxi.start_pos][current_task.destination]
                                    taxi.start_pos = current_task.destination
                                else:
                                    taxi.arrival_time = self.current_time + self.dist_mat[taxi.start_pos][current_task.origin]
                                    taxi.start_pos = current_task.origin
                            else:                           # no more task, always update arrival time as current time
                                taxi.arrival_time = self.current_time
                        else:  # initial step car's start_pos is not task origin or destination
                            self.taxi_key_loc[i].append((taxi.start_pos,self.current_time-(taxi.arrival_time<self.current_time)))
                            self.task_arr_time[i].append(taxi.arrival_time)
                            taxi.arrival_time += self.dist_mat[taxi.start_pos][current_task.origin] - (taxi.arrival_time<self.current_time)
                            taxi.start_pos = current_task.origin


            else: # it has no task, always update arrival time as current time
                self.total_idle_time += 1
                taxi.arrival_time = self.current_time


    def get_state(self):
        taxi_state = dict()
        for key in self.state_info.keys():
            if len(self.command[key]) == 0:
                taxi_state[key] = Taxi(self.state_info[key].start_pos, self.current_time, self.state_info[key].index)
            else:
                current_task = self.command[key][0]
                aval_time = current_task.vehDepOrigin + self.dist_mat[current_task.origin][current_task.destination]
                taxi_start_pos = current_task.destination
                taxi_state[key] = Taxi(taxi_start_pos, aval_time, self.state_info[key].index)
        return taxi_state
    
    def get_unloaded_passenger(self):
        unloaded_passenger = []
        for key in self.state_info.keys():
            if len(self.command[key]) > 0:
                unloaded_passenger += self.command[key][1:]
        result = dict()         
        for passenger in unloaded_passenger:
            o = passenger.origin
            d = passenger.destination
            t = passenger.pedArr
            idx = passenger.pedIndex
            p = Passenger(start = o, end = d, ocurr = t, index = idx)
            result[p.index] = p
            
        return result
    
    def get_time_cost(self, str= ""):
        self.total_waiting_time = 0
        taskPosStart = []
        taskPosEnd = []
        vehArrList = []
        pedArrList = []
        pedIdxList = []
        vehIdxList = []
        delayList = []
        for key in self.task_archive.keys():
            vehIdxList.append(key)
            taskIdx = []
            taxiArrTime = []
            pedArrTime = []
            pedDelay = []
            posStart = []
            posEnd = []
            for task in self.task_archive[key]:
                taskIdx.append(task.pedIndex)
                taxiArrTime.append(task.vehArrOrigin)
                pedArrTime.append(task.pedArr)
                self.total_waiting_time += max(task.vehArrOrigin - task.pedArr, 0)
                pedDelay.append(max(task.vehArrOrigin - task.pedArr, 0))
                posStart.append(task.origin)
                posEnd.append(task.destination)
            
            pedArrList.append(pedArrTime)
            vehArrList.append(taxiArrTime)
            pedIdxList.append(taskIdx)
            delayList.append(pedDelay)
            taskPosStart.append(posStart)
            taskPosEnd.append(posEnd)
            
        return (self.total_waiting_time, self.total_travel_time, self.total_idle_time)
            

