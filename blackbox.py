import sys
import os
import time
import json
from datetime import datetime

import tkinter as tk
from SimConnect import *
import numpy as np
import matplotlib.pyplot as plt


class DataRecorder:
    def __init__(self, simvars = []):
        self._status = "starting"
        self._init_simconnect(simvars)

    def _init_simconnect(self, simvars):
        """ Connect SimConnect to the Flight Simulator and set up the requests
        object. Prepare data dictionaries.

        Inputs:
        simvars - list, each element should be three elements long containing
                        the following: ["simvar", "readable name", "unit"]
        """
        print("Connecting via SimConnect...")
        self._simconnect = SimConnect()
        self._aq = AircraftRequests(self._simconnect, _time = 0)

        self._data_dict = {}
        self._name_dict = {}
        self._unit_dict = {}

        for var in simvars:
            key = simvars[0]
            name = simvars[1]
            unit = simvars[2]
            self._data_dict[key] = []
            self._name_dict[key] = name
            self._unit_dict[key] = unit

    def reset(self):
        """ (Re)set values tracking simulator state and (re)set data dictionaries. """
        self._airborne = False
        self._status = "starting"
        self._landing_time = 0
        self._airborne_list = [False]
        self._time_elapsed = []
        self._landing_data = None
        self._start_time = time.time()

        for key in self._data_dict:
            self._data_dict[key] = []

    def collect_latest_data(self):
        """ Collect data from the simulator via SimConnect.
        If the request times out, it will return -999999. In this case we keep
        the previous value (or set it to 0 if there are no values yet).        
        """
        aq = self._aq
        on_the_ground = aq.get("SIM_ON_GROUND")
        if on_the_ground == -999999:
            pass # keep the last value for self.airborne
        else:
            self.airborne = not on_the_ground
            if self.airborne and (self._status == "starting"
                                  or self._status == "taxiing out"):
                print("Takeoff detected...")
                self._status = "flying"

        self._airborne_list.append(self.airborne)
        if len(self._airborne_list) > 100:
            self._airborne_list.pop(0)

        for key, item in self._data_dict.items():
            item.append(round(aq.get(key), 2))
            if item[-1] == -999999:
                try:
                    item[-1] = item[-2]
                except IndexError:
                    item[-1] = 0

        time_elapsed = time.time() - self._start_time
        self._time_elapsed.append(time_elapsed)

        if self._status == "flying" and not any(self._airborne_list[-5:]):
            print("Landing detected...")
            self._status = "rollout"
            self._landing_time = time_elapsed
            self._landing_data = {"LANDING_TIME": self._landing_time}
            for key, item in self._data_dict.items():
                self._landing_data[key] = item[-1]

    @property
    def status(self):
        return self._status
    
    @property
    def data_dict(self):
        return self._data_dict.copy()

    @property
    def landing_data(self):
        return self._landing_data.copy()


if __name__ == "__main__":
    window = tk.Tk()
    window.title("Blackbox FS data recorder")

    window.rowconfigure(0, minsize=100, weight=1)
    window.columnconfigure(1, minsize=500, weight=1)

    frm_title = tk.Frame(master = window, bg = "#222222")
    frm_title.grid(row = 0, column = 0, sticky = "w")
    lbl_title = tk.Label(master = frm_title,
                         text = "Blackbox FS recorder",
                         bg = "#222222", fg = "white",
                         font=("Segoe UI", 16), width = 20)
    lbl_title.pack()

    frm_flightname = tk.Frame(master = window, bg = "#222222")
    frm_flightname.grid(row = 0, column = 1)
    ent_flightname = tk.Entry(master = frm_flightname, width = 20)
    ent_flightname.pack()

    frm_status = tk.Frame(master = window, bg = "#222222")
    frm_status.grid(row = 0, column = 2, sticky = "e")
    lbl_title = tk.Label(master = frm_status,
                         text = "Status: Loading",
                         bg = "#222222", fg = "white",
                         font=("Segoe UI", 16), width = 20)
    lbl_title.pack()

    window.mainloop()
