"""
* File: scenarioGenerator.py
* Author: Yi and Yushen
*
* created on 2024/10/02
"""

"""
@package scenarioGenerator.py
@brief This module generates the scenario to start the simulation run.

@dependencies
- dataCommon
"""

import os
import sys
import random

import pandas as pd
import numpy as np

from legacy_mod.dataCommon import Taxi, Passenger

class TaskGenerator:
    def __init__(self):
        pass
    
    def getScenarioInfo(self, config):
        
        total_pass = config.passNum
        total_taxi = config.taxiNum
        start_t = 0
        end_t = config.runTime
        interval = config.interval
        
        self.distrPath = "./inputs/downtown/" if config.city == "NYC" else "./inputs/Chicago_WNC/"
        self.scePath = "./instances/downtown/" if config.city == "NYC" else "./instances/chicago/"

        passenger_volume, passenger_list = self.load_passenger_volume(total_pass, total_taxi, end_t)
        taxi_volume, taxi_list = self.load_taxi_volume(total_pass, total_taxi, end_t)
        
        dist_matrix, wp_list = self.generate_dist_matrix()

        scenarioInfo = passenger_volume, taxi_volume, taxi_list, dist_matrix, wp_list 
        
        return scenarioInfo
        
    
    def generate_passenger_instance(self, total_num, min_t, max_t, time_interval, frequency, seed=None):
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        frequency.set_index('Unnamed: 0', inplace=True)
        
        origins = frequency.index.tolist()
        destinations = frequency.columns
        pairs = [(origin, destination) for origin in origins for destination in destinations]
        probabilities = frequency.values.flatten()

        probabilities /= probabilities.sum()
        
        passenger_dict = dict() 
        for i in range(total_num):
            sampled_pair = np.random.choice(len(pairs), p=probabilities)
            origin, destination = pairs[sampled_pair]
            sample_time = np.random.uniform(min_t, max_t)
            
            print(str(origin) + ', ' + str(destination))
            
            p = Passenger(start=origin, end= int(destination), ocurr=int(sample_time), index = i)

            idx = int(sample_time/time_interval)
            if(idx not in passenger_dict.keys()):
                passenger_dict[idx] = dict()
            passenger_dict[idx][p.index] = p
    
        return passenger_dict
        
        
    def generate_taxi_instance(self, total_num, min_t, frequency, seed=None):
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        taxi_dict = {}
        instance_list = []
        
        frequency.set_index('Unnamed: 0', inplace=True)
        
        origins = sorted(frequency.index.tolist())
        for i in range(total_num):
            origin = np.random.choice(origins)
            sample_time = min_t 
            t = Taxi(start_pos=origin, arrival_time=int(sample_time), index = i)
            taxi_dict[i] = t 
            instance_list.append(i)
            
        return taxi_dict, instance_list


    def generate_dist_matrix(self):
        travel_time = pd.read_csv(f'{self.distrPath}peak_travel_time.csv')
        travel_time.set_index('Unnamed: 0', inplace=True)

        origins = travel_time.index
        destinations = travel_time.columns
        
        dist_matrix = { idx: {int(d): int(row[d]) for d in destinations} for idx, row in travel_time.iterrows()}
                
        return dist_matrix, origins.to_list()
        
        
    def generate_fee_matrix(self, fee):
        
        fee.set_index('Unnamed: 0', inplace=True)
        
        origins = fee.index
        destinations = fee.columns
        
        fee_matrix = { idx: {int(d): row[d] for d in destinations} for idx, row in fee.iterrows()}
                
                
        return fee_matrix

    def generate_passenger_pair(self, pass_list):
        passenger_pair = []
        sorted_passengers = sorted(pass_list, key=lambda p: p.arrTime)
        for i in range(len(sorted_passengers)-1):
            for j in range(i+1, len(sorted_passengers)):
                passenger_pair.append([i, j])

        return passenger_pair, sorted_passengers

    def save_passenger_volume(self, passenger_volume, total_pass, total_taxi, end_t):
        filename = "passenger_volume_"+str(total_pass)+"pass_"+str(total_taxi)+"taxi_"+str(end_t)+"s.csv"
        """Save passenger volume dictionary to a CSV file."""
        data = []
        for time_slot, passengers in passenger_volume.items():
            for p_id, passenger in passengers.items():
                data.append([p_id, passenger.origin, passenger.destination, passenger.arrTime, time_slot])
        
        df = pd.DataFrame(data, columns=["passenger_id", "origin", "destination", "arrival_time", "time_slot"])
        df.to_csv(filename, index=False)
        print(f"Passenger volume saved to {filename}")

    def save_taxi_volume(self, taxi_volume, total_pass, total_taxi, end_t):
        filename = "taxi_volume_"+str(total_pass)+"pass_"+str(total_taxi)+"taxi_"+str(end_t)+"s.csv"
        """Save taxi volume dictionary to a CSV file."""
        data = [[taxi.index, taxi.start_pos, taxi.arrival_time] for taxi in taxi_volume.values()]
        
        df = pd.DataFrame(data, columns=["taxi_id", "start_pos", "arrival_time"])
        df.to_csv(filename, index=False)
        print(f"Taxi volume saved to {filename}")
        
        
    def load_passenger_volume(self, total_pass, total_taxi, end_t):
        """Load passenger volume from CSV and reconstruct passenger dictionary."""
        filename = self.scePath + "passenger_volume_"+str(total_pass)+"pass_"+str(total_taxi)+"taxi_"+str(end_t)+"s.csv"
        
        if not os.path.exists(filename):
            print(f"Error: specified scenario instance in cfg not found", file=sys.stderr)
            sys.exit(0)
    
        df = pd.read_csv(filename)
        
        passenger_volume = {}
        passenger_list = []

        for _, row in df.iterrows():
            passenger = Passenger(start=row["origin"], end=row["destination"], ocurr=row["arrival_time"], index=row["passenger_id"])
            passenger_list.append(passenger.index)

            time_slot = row["time_slot"]
            if time_slot not in passenger_volume:
                passenger_volume[time_slot] = {}
            passenger_volume[time_slot][passenger.index] = passenger

        print(f"Loaded {len(passenger_list)} passengers from {filename}")
        return passenger_volume, passenger_list

    def load_taxi_volume(self, total_pass, total_taxi, end_t):
        """Load taxi volume from CSV and reconstruct taxi dictionary."""
        filename = self.scePath + "taxi_volume_"+str(total_pass)+"pass_"+str(total_taxi)+"taxi_"+str(end_t)+"s.csv"
        
        if not os.path.exists(filename):
            print(f"Error: specified scenario instance in cfg not found", file=sys.stderr)
            sys.exit(0)
        
        df = pd.read_csv(filename)
        
        taxi_volume = {}
        taxi_list = []

        for _, row in df.iterrows():
            taxi = Taxi(start_pos=row["start_pos"], arrival_time=row["arrival_time"], index=row["taxi_id"])
            taxi_list.append(taxi.index)
            taxi_volume[taxi.index] = taxi

        print(f"Loaded {len(taxi_list)} taxis from {filename}")
        return taxi_volume, taxi_list
