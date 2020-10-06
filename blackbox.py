import sys
import os
import time
import json
from datetime import datetime

import pygame
from pygame.locals import *
from SimConnect import *
import numpy as np
import matplotlib.pyplot as plt


class Recorder:
    def __init__(self):
        self._running = True
        self._screen = None
        self._width = 1280
        self._height = 800
        self._size = (self._width, self._height)
        
        self.WHITE = (255, 255, 255)
        self.GREY1 = (15, 15, 15)
        self.GREY2 = (24, 24, 24)
        self.GREY3 = (44, 44, 44)
        self.RED = (255, 0, 0)
        self.DARKRED = (179, 0, 0)
        self.DARKERRED = (159, 0, 0)
        self.GREEN = (0, 255, 0)
        self.DARKGREEN = (0, 128, 0)
        self.DARKERGREEN = (0, 100, 0)
        self.BLUE = (0, 0, 255)
        self.BLACK = (0, 0, 0)

    def init_UI(self):
        pygame.init()
        pygame.display.set_caption("Blackbox")
        self._screen = pygame.display.set_mode(self._size, pygame.HWSURFACE | pygame.DOUBLEBUF)
        self._running = True

        pygame.font.init()
        self._fonts = {}
        for i in range(11, 30):
            self._fonts[i] = pygame.font.Font(os.path.join(os.getcwd(), "font", "Amble-Bold.ttf"), i)

        self._bg_box = pygame.Rect(0, 0, self._width, self._height)
        self._top_box = pygame.Rect(0, 0, self._width, 60)
        self._bottom_box = pygame.Rect(0, self._height - 60, self._width, 60)
        self._settings_box = pygame.Rect(0, self._height - 120, self._width, 60)

        self._stat_texts = {} # static texts
        self.setup_static_texts()
        self._clock = pygame.time.Clock()       

        self._mode = "preflight"
        self._usertext = ""
        self.init_simconnect()
        self._start_time = time.time()

    def setup_static_texts(self):
        self._stat_texts["Topleft title"] = self._fonts[19].render("Blackbox MSFS flight recorder",
                                                                   True, self.WHITE)
        self._stat_texts["Stdvals"] = self._fonts[17].render("Standard values:",
                                                             True, self.WHITE)
        self._stat_texts["Value"] = self._fonts[13].render("Value:",
                                                           True, self.WHITE)
        self._stat_texts["Curr"] = self._fonts[13].render("Curr:",
                                                          True, self.WHITE)
        self._stat_texts["Plot"] = self._fonts[13].render("Plot:",
                                                          True, self.WHITE)
        self._stat_texts["Row"] = self._fonts[13].render("Row:",
                                                         True, self.WHITE)
        self._stat_texts["Startrecord"] = self._fonts[25].render("Start recording",
                                                                 True, self.WHITE)
        self._stat_texts["Stoprecord"] = self._fonts[25].render("Stop recording",
                                                                True, self.WHITE)

    def on_event(self, event):
        if event.type == pygame.QUIT:
            self._running = False

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self._MB_pos[1] > self._height - 60:
                    if self._mode == "preflight":
                        self._mode = "recording"
                        self._start_time = time.time()
                    else:
                        self._mode = "preflight"
                        timestring = datetime.now().isoformat(timespec='minutes').replace(":", "")
                        self.make_plot(f"{timestring}.pdf")
                        self.store_json(f"{timestring}.json")
                        self.show_plot()
                        self.reset()

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self._usertext = self._usertext[:-1]
            else:
                add_text = event.unicode
                if len(self._usertext) < 100:
                    self._usertext += add_text

    def loop(self):
        self._MB_pos = pygame.mouse.get_pos()

        if self._mode == "recording":
            self.get_data()

        self._clock.tick_busy_loop(60)
        self.fps = self._clock.get_fps()

    def render(self):
        pygame.draw.rect(self._screen, self.GREY3, self._bg_box)
        pygame.draw.rect(self._screen, self.GREY2, self._top_box)
        pygame.draw.rect(self._screen, self.GREY2, self._settings_box)

        self._screen.blit(self._stat_texts["Topleft title"], (18, 18))
        self._screen.blit(self._stat_texts["Stdvals"], (18, 70))
        self._screen.blit(self._stat_texts["Value"], (18, 96))
        self._screen.blit(self._stat_texts["Curr"], (180, 96))

        text_y = 114
        for key, item in self.data_dict.items():
            text_name = self._fonts[15].render(self.data_units[key][0], True, self.WHITE)
            try:
                text_value = str(item[-1])
            except IndexError:
                text_value = "N/A"
            text_value = self._fonts[15].render(text_value, True, self.WHITE)
            self._screen.blit(text_name, (18, text_y))
            self._screen.blit(text_value, (180, text_y))
            text_y += text_value.get_height() + 3

        if self._mode == "preflight":
            text = self._stat_texts["Startrecord"]
            if self._MB_pos[1] < self._height - 60:
                color = self.DARKGREEN
            else:
                color = self.DARKERGREEN
            pygame.draw.rect(self._screen, color, self._bottom_box)
            self._screen.blit(text, (int(self._width/2 - text.get_width()/2), self._height - 45))
        elif self._mode == "recording":
            text = self._stat_texts["Stoprecord"]
            if self._MB_pos[1] < self._height - 60:
                color = self.DARKRED
            else:
                color = self.DARKERRED
            pygame.draw.rect(self._screen, color, self._bottom_box)
            self._screen.blit(text, (int(self._width/2 - text.get_width()/2), self._height - 45))

        pygame.display.flip()

    def cleanup(self):
        pygame.quit()

    def execute(self):
        if self.init_UI() == False:
            self._running = False
 
        while(self._running):
            for event in pygame.event.get():
                self.on_event(event)
            self.loop()
            self.render()
        self.cleanup()

    def init_simconnect(self):
        print("Connecting via SimConnect...")
        self._simconnect = SimConnect()
        self._aircraftrequests = AircraftRequests(self._simconnect, _time = 0)

        self.reset()
        self.data_units = {"VERTICAL_SPEED": ("Vertical speed", "ft/min"),
                           "AIRSPEED_TRUE": ("True airspeed", "knots"),
                           "AIRSPEED_INDICATED": ("Indicated airspeed", "knots"),
                           "GROUND_VELOCITY": ("Ground speed", "knots"),
                           "PLANE_ALT_ABOVE_GROUND": ("Radar altitude", "feet"),
                           "PLANE_ALTITUDE": ("Altitude (AMSL)", "feet"),
                           "G_FORCE": ("G-force", None)}
        print("Connected...")

    def reset(self):
        self.airborne = False
        self.has_been_airborne = False
        self.landing_detected = False
        self.landing_time = 0
        self.airborne_list = []
        self.time_elapsed = []
        self.landing_data = None

        ## Standard values
        self.data_dict = {"VERTICAL_SPEED": [],
                          "AIRSPEED_TRUE": [],
                          "AIRSPEED_INDICATED": [],
                          "GROUND_VELOCITY": [],
                          "PLANE_ALT_ABOVE_GROUND": [],
                          "PLANE_ALTITUDE": [],
                          "G_FORCE": []}

    def get_data(self):
        """ Collect data from the simulator via SimConnect """
        arq = self._aircraftrequests

        on_the_ground = arq.get("SIM_ON_GROUND")

        if on_the_ground == -999999:
            pass # keep the last value for self.airborne
        else:
            self.airborne = not on_the_ground
            if self.airborne and not self.has_been_airborne:
                print("Takeoff detected...")
                self.has_been_airborne = True

        self.airborne_list.append(self.airborne)
        if len(self.airborne_list) > 100:
            self.airborne_list.pop(0)

        for key, item in self.data_dict.items():
            item.append(round(arq.get(key), 2))
            if item[-1] == -999999:
                try:
                    item[-1] = item[-2]
                except IndexError:
                    item[-1] = 0

        time_elapsed = time.time() - self._start_time
        self.time_elapsed.append(time_elapsed)

        if self.has_been_airborne and not self.airborne and not self.landing_detected:
            print("\nLanding detected...")
            self.landing_detected = True
            self.landing_time = time_elapsed

            self.landing_data = self.data_dict.copy()
        
        speed_tot = np.sqrt(self.data_dict["VERTICAL_SPEED"][-1]**2
                                + self.data_dict["GROUND_VELOCITY"][-1]**2)

        if ((not any(self.airborne_list) or (speed_tot < 2 and not self.airborne))
                                                        # if the plane has been on the ground for at
                                                        # least 100 ticks, or it is standing still on the ground
                and time_elapsed > 50         # AND more than 50 seconds have passed since the logger was started
                and self.has_been_airborne    # AND the plane has at one point been airborne
                and speed_tot < 30):          # AND the speed of the aircarft is less than 30
            print("Auto-end [IMPLEMENT]")     # stop logging

    def make_plot(self, filename, skip_indices = 1):
        fig, axs = plt.subplots(2, 2, figsize = (13,10))
        axs[1, 0].plot(self.time_elapsed[::skip_indices],
                       self.data_dict["VERTICAL_SPEED"][::skip_indices],
                       label = "Vertical speed")
        axs[1, 0].set_xlabel("Time elapsed")
        axs[1, 0].set_ylabel("Speed [feet per minute]")
        axs[1, 0].legend()

        axs[0, 1].plot(self.time_elapsed[::skip_indices],
                       self.data_dict["AIRSPEED_TRUE"][::skip_indices],
                       label = "True airspeed")
        axs[0, 1].plot(self.time_elapsed[::skip_indices],
                       self.data_dict["GROUND_VELOCITY"][::skip_indices],
                       label = "Ground speed")
        axs[0, 1].plot(self.time_elapsed[::skip_indices],
                       self.data_dict["AIRSPEED_INDICATED"][::skip_indices],
                       label = "Indicated airspeed")
        axs[0, 1].set_xlabel("Time elapsed")
        axs[0, 1].set_ylabel("Speed [knots]")
        axs[0, 1].legend()

        axs[0, 0].plot(self.time_elapsed[::skip_indices],
                       self.data_dict["PLANE_ALT_ABOVE_GROUND"][::skip_indices],
                       label = "Radar altitude")
        axs[0, 0].plot(self.time_elapsed[::skip_indices],
                       self.data_dict["PLANE_ALTITUDE"][::skip_indices],
                       label = "Altitude (AMSL)")
        ground_level = (np.array(self.data_dict["PLANE_ALTITUDE"][::skip_indices])
                        - np.array(self.data_dict["PLANE_ALT_ABOVE_GROUND"][::skip_indices]))
        axs[0, 0].plot(self.time_elapsed[::skip_indices], ground_level,
                       label = "Ground level",
                       color = "green")
        axs[0, 0].set_xlabel("Time elapsed")
        axs[0, 0].set_ylabel("Altitude [feet]")
        axs[0, 0].legend()

        axs[1, 1].plot(self.time_elapsed[::skip_indices],
                       self.data_dict["G_FORCE"][::skip_indices],
                       label = "G-force")
        axs[1, 1].set_xlabel("Time elapsed")
        axs[1, 1].set_ylabel("G-force")
        axs[1, 1].legend()

        self.fig = fig
        self.axs = axs

        path = os.path.join(os.getcwd(), "plots", filename)
        self.fig.savefig(path, dpi = 300)

    def show_plot(self):
        """ Shows the latest figure """
        plt.show()

    def store_json(self, filename):
        path = os.path.join(os.getcwd(), "data", filename)
        store_dict = self.data_dict.copy()
        store_dict["ELAPSED_TIME"] = self.time_elapsed
        with open(path, "w") as outfile:
            json.dump(store_dict, outfile)
        

if __name__ == "__main__":
    recorder = Recorder()
    recorder.execute()