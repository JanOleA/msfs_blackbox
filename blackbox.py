import sys
import os
import time
import json
from datetime import datetime

import tkinter as tk
import tkinter.ttk as ttk
import ttkwidgets as ttkwdgt
import tkinter.font as tkFont
from SimConnect import *
import numpy as np
import matplotlib.pyplot as plt


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

        self.has_init = True
        self.reset()

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
            print("Resetting")
            self._airborne = False
            self._status = "starting"
            self._landing_time = 0
            self._airborne_list = [False]
            self._time_elapsed = []
            self._landing_data = {}
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

    def get_simvars(self):
        return self._simvars

    @property
    def simvars(self):
        return self._simvars

    @property
    def status(self):
        return self._status
    
    @property
    def data_dict(self):
        return self._data_dict.copy()

    @property
    def latest_data(self):
        ret_dict = {}
        for key, item in self._data_dict.items():
            ret_dict[key] = item[-1]
        return ret_dict

    @property
    def landing_data(self):
        return self._landing_data.copy()

    def make_plot(self, filename, tree_data, skip_indices = 1):
        """ Create and save the plot for the latest run. """
        remove_items = []
        for item in tree_data:
            if item[-1] == False:
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
            else:
                row = int(item[4]) - 1
                col = int(item[5]) - 1
                ax = axs[row, col]
            ax.plot(self._time_elapsed[::skip_indices],
                    self._data_dict[item[0]][::skip_indices],
                    label = self._name_dict[item[0]])
            ax.set_xlabel("Time elapsed")
            ax.set_ylabel(self._unit_dict[item[0]])
            ax.legend()

        path = os.path.join(os.getcwd(), "plots", filename)
        fig.savefig(path, dpi = 300)

    def show_plot(self):
        """ Shows the latest figure. """
        plt.show()

    def store_json(self, filename):
        """ Store the latest data as a JSON file. """
        path = os.path.join(os.getcwd(), "data", filename)
        store_dict = self.data_dict.copy()
        store_dict["ELAPSED_TIME"] = self._time_elapsed
        for key, item in self._landing_data.items():
            store_dict[f"LANDING_{key}"] = item
        with open(path, "w") as outfile:
            json.dump(store_dict, outfile)


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

        self._window.columnconfigure(0, minsize = 800, weight = 1)
        self._window.rowconfigure(1, minsize = 400, weight = 1)

        frm_topbar = tk.Frame(self._window)
        frm_topbar.grid(row = 0, column = 0, pady = 5)

        frm_topbar.columnconfigure(1, minsize = 400, weight = 1)

        lbl_title = tk.Label(frm_topbar,
                             text = "Blackbox FS recorder",
                             font=("Segoe UI", 12), width = 20)

        lbl_title.grid(row = 0, column = 0, sticky = "w")

        self._ent_flightname = tk.Entry(frm_topbar, width = 30,
                                        font =("Segoe UI", 11),
                                        justify = "center")
        self._ent_flightname.insert(0, "Name your flight")
        self._ent_flightname.grid(row = 0, column = 1)

        self._lbl_status = tk.Label(master = frm_topbar,
                              text = "Status: Loading",
                              font=("Segoe UI", 12), width = 20)
        self._lbl_status.grid(row = 0, column = 2, sticky = "e")

        frm_program = tk.Frame(self._window)
        frm_program.grid(row = 1, column = 0, sticky = "nw")
        frm_program.columnconfigure(0, minsize = 600, weight = 1)
        frm_program.rowconfigure(0, minsize = 600, weight = 1)

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

        self._btn_record.grid(row = 0, column = 0, sticky = "ew", padx = 5)
        self._btn_reset.grid(row = 0, column = 1, sticky = "ew")
        self._btn_cfgplot.grid(row = 0, column = 2, sticky = "ew", padx = 5)

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
                self._data_recorder.init_simconnect()
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
            self._data_recorder.make_plot(f"{flight_name.replace(' ', '_')}.pdf", self.tree_items)
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

        for item in default_simvars:
            item += ["N/A", 1, 1]
            self._tree_simvars.insert("", "end", values = item)

        rows = self._tree_simvars.get_children()
        for row in rows:
            self._tree_simvars.change_state(row, "checked")

    def record_loop(self):
        dr = self._data_recorder
        if self._recording:
            dr.collect_latest_data()
            latest_data = dr.latest_data
            rows = self._tree_simvars.get_children()
            for row in rows:
                values = self._tree_simvars.item(row)["values"]
                key, name, unit = values[:3]
                prow, pcol = values[4:]
                self._tree_simvars.item(row, values = [key, name, unit,
                    	                               latest_data[key],
                                                       prow, pcol])
        
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
                       ]

    
    window = Window_BB(default_simvars)
    window.mainloop()