import sys
import os
import time
import json
from datetime import datetime
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkFont

import ttkwidgets as ttkwdgt
from SimConnect import *
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d


class DataRecorder:
    def __init__(self, simvars = []):
        self._status = "starting"
        self._simvars = simvars
        self.has_init = False

        self._data_dict = {}
        self._name_dict = {}
        self._unit_dict = {}

        for var in self._simvars:
            key = var[0]
            name = var[1]
            unit = var[2]
            self._data_dict[key] = []
            self._name_dict[key] = name
            self._unit_dict[key] = unit

    def init_simconnect(self):
        """ Connect SimConnect to the Flight Simulator and set up the requests
        object.
        """
        print("Connecting via SimConnect...")
        self._simconnect = SimConnect()
        self._aq = AircraftRequests(self._simconnect, _time = 0)
        self.ae = AircraftEvents(self._simconnect)

        self.toggle_pushback = self.ae.find("TOGGLE_PUSHBACK")
        self._set_pushback_angle = self.ae.find("KEY_TUG_HEADING")
        self.select_1 = self.ae.find("SELECT_1")
        self.select_2 = self.ae.find("SELECT_2")

        self.has_init = True
        self.reset()

    def set_pushback_angle(self, angle):
        self._set_pushback_angle(angle)

    def set_simvars(self, simvars = []):
        """ Add new simvars and remove those no longer included in 'simvars'
        from the data dictionary.
        """
        keys = []
        for var in simvars:
            key = var[0]
            name = var[1]
            unit = var[2]
            keys.append(key)
            if key in self._simvars:
                continue
            self._data_dict[key] = []
            self._name_dict[key] = name
            self._unit_dict[key] = unit

        del_keys = []
        for key in self._data_dict:
            if not key in keys:
                del_keys.append(key)
        
        for key in del_keys:
            del self._data_dict[key]
            del self._name_dict[key]
            del self._unit_dict[key]

    def reset(self):
        """ (Re)set values tracking simulator state and (re)set data dictionaries. """
        if self.has_init:
            self._airborne = False
            self._status = "starting"
            self._landing_time = 0
            self._airborne_list = [False]
            self._time_elapsed = []
            self._events = []
            self._landing_data = {}
            self._takeoff_data = {}
            self._start_time = time.time()

            for key in self._data_dict:
                self._data_dict[key] = []

    def get_simvars(self):
        return self._simvars

    def get_pushback_state(self):
        if self.has_init:
            return self._aq.get("PUSHBACK_STATE")
        else:
            print(f"Attempted to pushback before init. Start recording first.")

    def collect_latest_data(self):
        """ Collect data from the simulator via SimConnect.
        Stores the history of the data in the `data_dict` dictionary
        """
        self._events = []
        aq = self._aq
        on_the_ground = aq.get("SIM_ON_GROUND")
        if on_the_ground == -999999:
            pass # keep the last value for self.airborne
            if not hasattr(self, "airborne"):
                self.airborne = False
        else:
            self.airborne = not on_the_ground
            
        self._airborne_list.append(self.airborne)
        if len(self._airborne_list) > 100:
            self._airborne_list.pop(0)

        for key, item in self._data_dict.items():
            try:
                item.append(round(aq.get(key), 4))
            except Exception as e:
                item.append(-999999)

        time_elapsed = time.time() - self._start_time
        self._time_elapsed.append(time_elapsed)

        if (self.airborne
                and (self._status == "starting"
                     or self._status == "taxiing out")
                and len(self._airborne_list) > 2):
            if all(self._airborne_list[-3:]):
                print("Takeoff detected...")
                self._status = "flying"

                for key, item in self._data_dict.items():
                    item_ = np.array(item[-3:])
                    item_ = item_[item_ != -999999]
                    if len(item_) == 0:
                        item_ = [-999999]
                    self._takeoff_data[key] = item[-3:-1]

                self._events.append("takeoff")

        if self._status == "flying" and not any(self._airborne_list[-3:]) and not "takeoff" in self._events:
            print("Landing detected...")
            self._status = "rollout"
            self._landing_time = time_elapsed
            self._landing_data = {"LANDING_TIME": self._landing_time}
            for key, item in self._data_dict.items():
                item_ = np.array(item[-4:])
                item_ = item_[item != -999999]
                if len(item_) == 0:
                    item_ = [-999999]
                self._landing_data[key] = item_

            self._events.append("landing")

    @property
    def simvars(self):
        return self._simvars

    @property
    def status(self):
        return self._status
    
    @property
    def time_elapsed(self):
        return self._time_elapsed[-1]

    @property
    def data_dict(self):
        return self._data_dict.copy()

    @property
    def name_dict(self):
        return self._name_dict

    @property
    def latest_data(self):
        ret_dict = {}
        for key, item in self._data_dict.items():
            ret_dict[key] = item[-1]
        return ret_dict

    @property
    def landing_data(self):
        return self._landing_data.copy()

    @property
    def takeoff_data(self):
        return self._takeoff_data.copy()

    @property
    def events(self):
        return self._events

    def make_plot(self, filename, tree_data, skip_indices = 1):
        """ Create and save the plot for the latest run. """
        remove_items = []
        for item in tree_data:
            if item[-1] == False:
                # remove items with disabled plot tickbox
                remove_items.append(item)
        for item in remove_items:
            tree_data.remove(item)

        tree_data = np.array(tree_data)
        rows = tree_data[:,4].astype(int)
        cols = tree_data[:,5].astype(int)
        max_rows = rows.max()
        max_cols = cols.max()

        fig, axs = plt.subplots(max_rows, max_cols, figsize = (13,10))

        for item in tree_data:
            if max_rows == max_cols == 1:
                ax = axs
            elif max_rows == 1:
                col = int(item[5]) - 1
                ax = axs[col]
            elif max_cols == 1:
                row = int(item[4]) - 1
                ax = axs[row]
            else:
                row = int(item[4]) - 1
                col = int(item[5]) - 1
                ax = axs[row, col]

            ax.plot(self._time_elapsed[1:-1:skip_indices],
                    self._data_dict[item[0]][1:-1:skip_indices],
                    label = self._name_dict[item[0]])
            ax.set_xlabel("Time elapsed")
            ax.set_ylabel(self._unit_dict[item[0]])
            ax.legend()

        path = os.path.join(os.getcwd(), "plots", filename)
        fig.savefig(path, dpi = 300)

    def show_plot(self):
        """ Shows the latest figure. """
        plt.show()

    def clean_data(self):
        """ Interpolates for the values where SimConnect returned -999999 """
        for key, item in self._data_dict.items():
            y = np.array(item)
            if y[-1] == -999999:
                y[-1] = y[y != -999999][-1]
            if y[0] == -999999:
                y[0] = y[y != -999999][0]
            x = np.arange(len(y))
            idx = np.where(y != -999999)
            try:
                f = interp1d(x[idx], y[idx])
                self._data_dict[key] = f(x)
            except Exception as e:
                print(f"Couldn't interpolate {key}: {e}")         
                print(min(item[item != -999999]))   


    def store_json(self, filename):
        """ Store the latest data as a JSON file. """
        try:
            path = os.path.join(os.getcwd(), "data", filename)
            store_dict = self.data_dict.copy()
            store_dict["ELAPSED_TIME"] = self._time_elapsed
            for key, item in self._landing_data.items():
                try:
                    store_dict[f"LANDING_{key}"] = item.tolist()
                except Exception as e:
                    print(f"Attempted converting {key} to list. Failed because: {e}")
            for key, item in store_dict.items():
                try:
                    store_dict[key] = item.tolist()
                except Exception as e:
                    print(f"Attempted converting {key} to list. Failed because: {e}")
            with open(path, "w") as outfile:
                json.dump(store_dict, outfile)
        except Exception as e:
            print(f"Couldn't save as JSON: {e}")


class Window_BB:
    def __init__(self, default_simvars):
        self._default_simvars = default_simvars
        self._data_recorder = DataRecorder(default_simvars)
        self._make_ui()
        self._setup_tree()
        self._recording = False
        self._lbl_status["text"] = "Status: Ready"

    def _make_ui(self):
        """ Setup the UI elements. """
        self._window = tk.Tk()
        self._window.title("Blackbox FS data recorder")

        self._window.columnconfigure(0, weight = 1)
        self._window.rowconfigure(1, weight = 1)

        frm_topbar = tk.Frame(self._window)
        frm_topbar.grid(row = 0, column = 0, pady = 5)

        frm_topbar.columnconfigure(1, weight = 1)

        lbl_title = tk.Label(frm_topbar,
                             text = "Blackbox FS recorder",
                             font=("Segoe UI", 12), width = 25)

        lbl_title.grid(row = 0, column = 0, sticky = "w")

        self._ent_flightname = tk.Entry(frm_topbar, width = 30,
                                        font =("Segoe UI", 11),
                                        justify = "center")
        self._ent_flightname.insert(0, "Name your flight")
        self._ent_flightname.grid(row = 0, column = 1)

        self._lbl_status = tk.Label(master = frm_topbar,
                              text = "Status: Loading",
                              font=("Segoe UI", 12), width = 25)
        self._lbl_status.grid(row = 0, column = 2, sticky = "e")

        frm_program = tk.Frame(self._window)
        frm_program.grid(row = 1, column = 0, sticky = "nw")

        frm_leftmenu = tk.Frame(frm_program)
        frm_leftmenu.grid(row = 0, column = 0, sticky = "nw")

        frm_top_buttons = tk.Frame(frm_leftmenu)
        frm_top_buttons.grid(row = 0, column = 0, sticky = "ew", pady = 5)

        self._btn_record = tk.Button(frm_top_buttons, text = "Start",
                                     command = self.toggle_recording, width = 10)
        self._btn_reset = tk.Button(frm_top_buttons, text = "Reset",
                                    command = self.reset_data, width = 10)
        self._btn_cfgplot = tk.Button(frm_top_buttons, text = "Configure plot",
                                      command = self.cfg_plot, width = 20)
        self._btn_savesettings = tk.Button(frm_top_buttons, text = "Save settings",
                                           command = self._save_settings, width = 20)

        self._btn_record.grid(row = 0, column = 0, sticky = "ew", padx = 5)
        self._btn_reset.grid(row = 0, column = 1, sticky = "ew")
        self._btn_cfgplot.grid(row = 0, column = 2, sticky = "ew", padx = 5)
        self._btn_savesettings.grid(row = 0, column = 3, sticky = "ew")

        lbl_tracking = tk.Label(frm_leftmenu, text = "Tracking variables:")
        lbl_tracking.grid(row = 2, column = 0, sticky = "s", padx = 5, pady = 3)

        self._cols_tree = ["simvar", "name", "unit", "value", "prow", "pcol"]
        container_tree = ttk.Frame(frm_leftmenu)
        container_tree.grid(row = 3, column = 0, sticky = "ew", padx = 5)
        self._tree_simvars = ttkwdgt.CheckboxTreeview(container_tree,
                                                      columns = self._cols_tree,
                                                      show = ("headings", "tree"),
                                                      height = 15)
        vsb = ttk.Scrollbar(container_tree, orient = "vertical", command = self._tree_simvars.yview)
        self._tree_simvars.configure(yscrollcommand = vsb.set)

        self._tree_simvars.grid(row = 0, column = 0, sticky = "nsew")
        vsb.grid(row = 0, column = 1, sticky = "ns")
        container_tree.grid_columnconfigure(0, weight=1)
        container_tree.grid_rowconfigure(0, weight=1)

        self._btn_deleteitem = tk.Button(frm_leftmenu, text = "Remove selected item",
                                         command = self.remove_current_from_tree)
        self._btn_deleteitem.grid(row = 4, column = 0, sticky = "ew", padx = 5, pady = 5)

        lbl_addnew = tk.Label(frm_leftmenu, text = "Add variable to track:")
        lbl_addnew.grid(row = 5, column = 0, sticky = "s", padx = 5)

        self._frm_newentries = tk.Frame(frm_leftmenu)
        self._frm_newentries.grid(row = 6, column = 0, sticky = "ew", padx = 5)

        self._ent_newsimvar = tk.Entry(self._frm_newentries, width = 20,
                                       font =("Segoe UI", 11))
        self._ent_newname = tk.Entry(self._frm_newentries, width = 20,
                                     font =("Segoe UI", 11))
        self._ent_newunit = tk.Entry(self._frm_newentries, width = 8,
                                     font =("Segoe UI", 11))
        self._ent_newsimvar.grid(row = 0, column = 0)
        self._ent_newname.grid(row = 0, column = 1)
        self._ent_newunit.grid(row = 0, column = 2)

        btn_addnew = tk.Button(self._frm_newentries, text = "Add", command = self.add_new_to_tree, width = 12)
        btn_addnew.grid(row = 0, column = 3, sticky = "ew", padx = 5, pady = 3)

        self._lbl_lastevent = tk.Label(frm_program, text = "No recent events")
        self._lbl_lastevent.grid(row = 2, column = 0, sticky = "sw", padx = 5, pady = 5)

        """

        frm_pushback_helper = ttk.Frame(frm_program)
        frm_pushback_helper.grid(row = 0, column = 1, sticky = "nw")

        frm_pushback_label = ttk.Frame(frm_pushback_helper)
        frm_pushback_label.grid(row = 0, column = 0, sticky = "nsew")

        lbl_pushback_helper = ttk.Label(frm_pushback_label, text = "Pushback helper", justify = "center")
        lbl_pushback_helper.pack()

        frm_leftpush = ttk.Frame(frm_pushback_helper)
        frm_leftpush.grid(row = 1, column = 0, sticky = "nsew")

        frm_ctrpush = ttk.Frame(frm_pushback_helper)
        frm_ctrpush.grid(row = 1, column = 1, sticky = "nsew")

        frm_rightpush = ttk.Frame(frm_pushback_helper)
        frm_rightpush.grid(row = 1, column = 2, sticky = "nsew")

        frm_pushback_helper.columnconfigure(0, weight = 1)
        frm_pushback_helper.columnconfigure(1, weight = 1)
        frm_pushback_helper.columnconfigure(2, weight = 1)

        frm_pushback_helper.rowconfigure(0, weight = 0)

        btn_pushback_left = ttk.Button(frm_leftpush, text = "←", 
                                       command = self.set_pushback_left)
        btn_pushback_left.pack(fill = tk.BOTH, expand = 1)

        btn_pushback_stop = ttk.Button(frm_ctrpush, text = "Stop", 
                                       command = self.set_pushback_stop)
        btn_pushback_stop.pack()

        btn_pushback_back = ttk.Button(frm_ctrpush, text = "↓", 
                                       command = self.set_pushback_backwards)
        btn_pushback_back.pack()

        btn_pushback_rigt = ttk.Button(frm_rightpush, text = "→", 
                                       command = self.set_pushback_right)
        btn_pushback_rigt.pack(fill = tk.BOTH, expand = 1)

        self._pushback_status = 3 # 3 = stopped, 2 = right, 1 = left, 0 = backwards"""

    def disable_frame(self, frame):
        """ Disable all items in a frame """
        for child in frame.winfo_children():
            child.configure(state="disabled")

    def enable_frame(self, frame):
        """ Enable all items in a frame """
        for child in frame.winfo_children():
            child.configure(state="normal")

    def reset_data(self):
        self._data_recorder.reset()
        self._btn_record.configure(state = "normal")
        self._lbl_status["text"] = "Status: Ready"

    def toggle_recording(self):
        if not self._recording:
            self._recording = True
            self._btn_record["text"] = "Stop"
            self.disable_frame(self._frm_newentries)
            self._btn_reset.configure(state = "disabled")
            self._btn_deleteitem.configure(state = "disabled")
            self._ent_flightname.configure(state = "disabled")
            if not self._data_recorder.has_init:
                print("init_simconnect")
                self._data_recorder.init_simconnect()
            self._data_recorder.reset()
            self._lbl_status["text"] = "Status: Recording"
        else:
            self._recording = False
            self._btn_record["text"] = "Start"
            self.enable_frame(self._frm_newentries)
            self._btn_reset.configure(state = "normal")
            self._btn_deleteitem.configure(state = "normal")
            self._lbl_status["text"] = "Status: Recording stopped"
            self._btn_record.configure(state = "disabled")
            self._ent_flightname.configure(state = "normal")
            flight_name = self._ent_flightname.get()
            if flight_name == "Name your flight":
                flight_name = "unnamed"
            self._data_recorder.clean_data()
            self._data_recorder.make_plot(f"{flight_name.replace(' ', '_')}.pdf", self.tree_items)
            self._data_recorder.store_json(f"{flight_name.replace(' ', '_')}.json")
            self._data_recorder.show_plot()

    def cfg_plot(self):
        self._btn_cfgplot.configure(state = "disabled")
        self._cfg_plot_window = tk.Tk()
        self._cfg_plot_window.title("Configure plot")

        top_frame = tk.Frame(self._cfg_plot_window)
        top_frame.columnconfigure(0, minsize = 200)
        top_frame.columnconfigure(1, minsize = 60)
        top_frame.columnconfigure(2, minsize = 60)
        rows = self._tree_simvars.get_checked()
        items = {}
        for row in rows:
            items[row] = self._tree_simvars.item(row)["values"]

        lbl_name = tk.Label(top_frame, text = "Name", font = ("Segoe UI", 10, "bold"))
        lbl_name.grid(row = 0, column = 0)
        lbl_row = tk.Label(top_frame, text = "Plot Row", font = ("Segoe UI", 10, "bold"))
        lbl_row.grid(row = 0, column = 1)
        lbl_col = tk.Label(top_frame, text = "Plot Col", font = ("Segoe UI", 10, "bold"))
        lbl_col.grid(row = 0, column = 2)

        i = 1
        bgcolors = ["#FDFDFD", "#EBEBEB"]
        self._entries = {}
        for key, item in items.items():
            frm_item = tk.Frame(top_frame, width = 200, height = 40, bg = bgcolors[i%2])
            frm_item.grid(row = i, column = 0)
            lbl_item = tk.Label(frm_item, text = item[1])
            lbl_item.pack()
            frm_plotrow = tk.Frame(top_frame, width = 60)
            frm_plotcol = tk.Frame(top_frame, width = 60)
            frm_plotrow.grid(row = i, column = 1)
            frm_plotcol.grid(row = i, column = 2, padx = 2, pady = 4)
            ent_plotrow = tk.Entry(frm_plotrow, justify = "center", width = 7)
            ent_plotcol = tk.Entry(frm_plotcol, justify = "center", width = 7)
            ent_plotrow.pack()
            ent_plotcol.pack()
            ent_plotrow.insert(0, item[4])
            ent_plotcol.insert(0, item[5])
            self._entries[key] = [ent_plotrow, ent_plotcol]
            i += 1

        top_frame.pack()

        btn_save = tk.Button(self._cfg_plot_window, text = "Confirm", width = 20,
                             command = self._store_plot_cols)
        btn_save.pack(pady = 5)

        self._cfg_plot_window.protocol("WM_DELETE_WINDOW", self._store_plot_cols)

    def _store_plot_cols(self):
        self._btn_cfgplot.configure(state = "normal")
        for row, item in self._entries.items():
            prow = item[0].get()
            pcol = item[1].get()
            values = self._tree_simvars.item(row)["values"]
            key, name, unit, latest_data = values[:4]
            self._tree_simvars.item(row, values = [key, name, unit,
                    	                           latest_data,
                                                   prow, pcol])
        self._cfg_plot_window.destroy()

    def remove_current_from_tree(self):
        current = self._tree_simvars.focus()
        self._tree_simvars.delete(current)

        self._data_recorder.set_simvars(self.tree_items)

    def add_new_to_tree(self):
        simvar = self._ent_newsimvar.get().upper().replace(" ", "_")
        name = self._ent_newname.get()
        unit = self._ent_newunit.get()

        if (simvar == ""
            or name == ""
            or unit == ""):
            tk.messagebox.showinfo(title = "Invalid entry",
                                   message = "You need to enter a value in each field!")
            return

        for item in self.tree_items:
            if item[0] == simvar:
                tk.messagebox.showinfo(title = "Invalid entry",
                                       message = "Entry already exists!")
                return
        
        self._tree_simvars.insert("", "end", values = (simvar, name, unit, "N/A", 1, 1))
        self._ent_newsimvar.delete(0, tk.END)
        self._ent_newname.delete(0, tk.END)
        self._ent_newunit.delete(0, tk.END)

        self._data_recorder.set_simvars(self.tree_items)

    def get_tree_items(self):
        rows = self._tree_simvars.get_children()
        checked = self._tree_simvars.get_checked()
        ret_list = []
        for row in rows:
            if row in checked:
                this_checked = True
            else:
                this_checked = False
            ret_list.append(self._tree_simvars.item(row)["values"] + [this_checked])
        return ret_list

    def angle_converter(self, angle):
        """ Converts from an angle to a 32 bit integer representing that angle
        from 0 to 4294967295.
        """
        angle /= 360 # first normalize the angle
        angle *= 4294967295 # multiply to convert
        angle = int(angle) # convert to int

        return angle

    def set_pushback_backwards(self):
        state = int(self._data_recorder.get_pushback_state())
        if state == 3:
            print("start backwards")
            self._data_recorder.toggle_pushback()
            self._data_recorder.set_pushback_angle(0)
        elif state == 0 or state == 1 or state == 2:
            print("set angle to 0")
            self._data_recorder.set_pushback_angle(0)

    def set_pushback_left(self):
        state = int(self._data_recorder.get_pushback_state())
        if state == 0 or state == 1 or state == 2:
            self._data_recorder.set_pushback_angle(45)

    def set_pushback_right(self):
        state = int(self._data_recorder.get_pushback_state())
        if state == 0 or state == 1 or state == 2:
            self._data_recorder.set_pushback_angle(315)

    def set_pushback_stop(self):
        state = int(self._data_recorder.get_pushback_state())
        if state != 3:
            print("stop")
            self._data_recorder.toggle_pushback()

    def _save_settings(self):
        items = self.tree_items
        with open(os.path.join(os.getcwd(), "settings.json"), "w") as outfile:
            json.dump(items, outfile)

    @property
    def tree_items(self):
        return self.get_tree_items()

    def _setup_tree(self):
        default_simvars = self._default_simvars
        self._tree_simvars.heading("#0", text = "Plot")
        self._tree_simvars.column("#0", width = 50)
        for col in self._cols_tree:
            self._tree_simvars.heading(col, text = col.title())

        displaycolumns = list(self._tree_simvars["columns"])
        displaycolumns.remove("prow")
        displaycolumns.remove("pcol")

        self._tree_simvars["displaycolumns"] = displaycolumns

        self._tree_simvars.column("simvar", width = 175)
        self._tree_simvars.column("name", width = 140)
        self._tree_simvars.column("unit", width = 50)
        self._tree_simvars.column("value", width = 60)

        if os.path.isfile(os.path.join(os.getcwd(), "settings.json")):
            with open(os.path.join(os.getcwd(), "settings.json"), "r") as infile:
                items = json.load(infile)
            for item in items:
                self._tree_simvars.insert("", "end", values = item[:-1])
                if item[-1]:
                    row = self._tree_simvars.get_children()[-1]
                    self._tree_simvars.change_state(row, "checked")
                    

        else:
            for item in default_simvars:
                item += ["N/A", 1, 1]
                self._tree_simvars.insert("", "end", values = item)

            rows = self._tree_simvars.get_children()
            for row in rows:
                self._tree_simvars.change_state(row, "checked")

    def record_loop(self):
        """ Collect latest data and display it to the user """
        dr = self._data_recorder
        if self._recording:
            dr.collect_latest_data()
            latest_data = dr.latest_data

            if "takeoff" in dr.events:
                text = f"Takeoff at {dr.time_elapsed:.1f} s | "
                for key, item in dr.takeoff_data.items():
                    try:
                        name = dr.name_dict[key]
                    except KeyError:
                        continue
                    if key == "G_FORCE":
                        text += f"{name}: {np.average(item):.2f} | "
                    if key == "AIRSPEED_INDICATED" or key == "GROUND_VELOCITY":
                        text += f"{name}: {np.average(item):.0f} kts | "
                self._lbl_lastevent["text"] = text

            if "landing" in dr.events:
                text = f"Landing at {dr.time_elapsed:.1f} s | "
                for key, item in dr.landing_data.items():
                    try:
                        name = dr.name_dict[key]
                    except KeyError:
                        continue
                    if key == "G_FORCE":
                        item = np.max(item)
                        text += f"{name}: {item:.2f} | "
                    if key == "VERTICAL_SPEED":
                        item = np.min(item)
                        text += f"{name}: {item:.0f} ft/min | "
                    if key == "AIRSPEED_INDICATED" or key == "GROUND_VELOCITY":
                        text += f"{name}: {np.average(item):.0f} kts | "

                self._lbl_lastevent["text"] = text

            rows = self._tree_simvars.get_children()
            for row in rows:
                values = self._tree_simvars.item(row)["values"]
                key, name, unit = values[:3]
                last_val = values[3]
                if latest_data[key] == -999999:
                    new_val = last_val
                else:
                    new_val = latest_data[key]
                prow, pcol = values[4:]
                self._tree_simvars.item(row, values = [key, name, unit,
                    	                               new_val, prow, pcol])
        
        self._window.after(250, self.record_loop)

    def mainloop(self):
        self._window.after(250, self.record_loop)
        self._window.mainloop()


if __name__ == "__main__":
    default_simvars = [["VERTICAL_SPEED",           "Vertical speed",       "ft/min"],
                       ["AIRSPEED_TRUE",            "True airspeed",        "knots"],
                       ["AIRSPEED_INDICATED",       "Indicated airspeed",   "knots"],
                       ["GROUND_VELOCITY",          "Ground speed",         "knots"],
                       ["PLANE_ALT_ABOVE_GROUND",   "Altitude (grnd)",      "feet"],
                       ["PLANE_ALTITUDE",           "Altitude (AMSL)",      "feet"],
                       ["G_FORCE",                  "G-force",              "g"],
                       ["PLANE_LATITUDE",           "GPS Latitude",         "deg"],
                       ["PLANE_LONGITUDE",          "GPS Longitude",        "deg"],
                       ]

    

    window = Window_BB(default_simvars)
    window.mainloop()