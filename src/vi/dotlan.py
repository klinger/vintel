###########################################################################
#  Vintel - Visual Intel Chat Analyzer									  #
#  Copyright (C) 2014-15 Sebastian Meyer (sparrow.242.de+eve@gmail.com )  #
#																		  #
#  This program is free software: you can redistribute it and/or modify	  #
#  it under the terms of the GNU General Public License as published by	  #
#  the Free Software Foundation, either version 3 of the License, or	  #
#  (at your option) any later version.									  #
#																		  #
#  This program is distributed in the hope that it will be useful,		  #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of		  #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the		  #
#  GNU General Public License for more details.							  #
#																		  #
#																		  #
#  You should have received a copy of the GNU General Public License	  #
#  along with this program.	 If not, see <http://www.gnu.org/licenses/>.  #
###########################################################################

###########################################################################
# Little lib and tool to get the map and information from dotlan		  #
###########################################################################

import logging
import math
import time

import requests
import six
from bs4 import BeautifulSoup
from vi import states
from vi.cache.cache import Cache

from . import evegate


class DotlanException(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)


class Map(object):
    """
        The map including all information from dotlan
    """

    DOTLAN_BASIC_URL = u"http://evemaps.dotlan.net/svg/{0}.svg"

    @property
    def svg(self):
        # Re-render all systems
        for system in self.systems.values():
            system.update()
        # Update the marker
        if not self.marker["opacity"] == "0":
            now = time.time()
            new_value = (1 - (now - float(self.marker["activated"])) / 10)
            if new_value < 0:
                new_value = "0"
            self.marker["opacity"] = new_value
        content = str(self.soup)
        return content

    def __init__(self, region, svg_file=None):
        self.region = region
        cache = Cache()
        self.outdatedCacheError = None

        # Get map from dotlan if not in the cache
        if not svg_file:
            svg = cache.get_fromcache("map_" + self.region)
        else:
            svg = svg_file
        if not svg:
            try:
                svg = self._get_svg_from_dotlan(self.region)
                cache.put_into_cache("map_" + self.region, svg, evegate.seconds_till_downtime() + 60 * 60)
            except Exception as e:
                self.outdatedCacheError = e
                svg = cache.get_fromcache("map_" + self.region, True)
                if not svg:
                    t = "No Map in cache, nothing from dotlan. Must give up " \
                        "because this happened:\n{0} {1}\n\nThis could be a " \
                        "temporary problem (like dotlan is not reachable), or " \
                        "everythig went to hell. Sorry. This makes no sense " \
                        "without the map.\n\nRemember the site for possible " \
                        "updates: https://github.com/Xanthos-Eve/vintel".format(type(e), six.text_type(e))
                    raise DotlanException(t)
        # Create soup from the svg
        self.soup = BeautifulSoup(svg, 'html.parser')
        self.systems = self._extract_systems_from_soup(self.soup)
        self.systemsById = {}
        for system in self.systems.values():
            self.systemsById[system.systemId] = system
        self._prepare_svg(self.soup, self.systems)
        self._connect_neighbours()
        self._statisticsVisible = False
        self.marker = self.soup.select("#select_marker")[0]

    def _extract_systems_from_soup(self, soup):
        systems = {}
        uses = {}
        for use in soup.select("use"):
            use_id = use["xlink:href"][1:]
            uses[use_id] = use
        symbols = soup.select("symbol")
        for symbol in symbols:
            symbol_id = symbol["id"]
            system_id = symbol_id[3:]
            try:
                system_id = int(system_id)
            except ValueError as e:
                continue
            for element in symbol.select(".sys"):
                name = element.select("text")[0].text.strip().upper()
                map_coordinates = {}
                for keyname in ("x", "y", "width", "height"):
                    map_coordinates[keyname] = float(uses[symbol_id][keyname])
                map_coordinates["center_x"] = (map_coordinates["x"] + (map_coordinates["width"] / 2))
                map_coordinates["center_y"] = (map_coordinates["y"] + (map_coordinates["height"] / 2))
                try:
                    transform = uses[symbol_id]["transform"]
                except KeyError:
                    transform = "translate(0,0)"
                systems[name] = System(name, element, self.soup, map_coordinates, transform, system_id)
        return systems

    def _prepare_svg(self, soup, systems):
        svg = soup.select("svg")[0]
        # Disable dotlan mouse functionality and make all jump lines black
        svg["onmousedown"] = "return false;"
        for line in soup.select("line"):
            line["class"] = "j"

        # Current system marker ellipse
        group = soup.new_tag("g", id="select_marker", opacity="0", activated="0", transform="translate(0, 0)")
        ellipse = soup.new_tag("ellipse", cx="0", cy="0", rx="56", ry="28", style="fill:#462CFF")
        group.append(ellipse)

        # The giant cross-hairs
        for coord in ((0, -10000), (-10000, 0), (10000, 0), (0, 10000)):
            line = soup.new_tag("line", x1=coord[0], y1=coord[1], x2="0", y2="0", style="stroke:#462CFF")
            group.append(line)
        svg.insert(0, group)

        # Set up the tags for system statistics
        for systemId, system in self.systemsById.items():
            coords = system.mapCoordinates
            text = "stats n/a"
            style = "text-anchor:middle;font-size:8;font-weight:normal;font-family:Arial;"
            svgtext = soup.new_tag("text", x=coords["center_x"], y=coords["y"] + coords["height"] + 6, fill="blue",
                                   style=style, visibility="hidden", transform=system.transform)
            svgtext["id"] = "stats_" + str(systemId)
            svgtext["class"] = ["statistics", ]
            svgtext.string = text

    def _connect_neighbours(self):
        """
            This will find all neighbours of the systems and connect them.
            It takes a look at all the jumps on the map and gets the system under
            which the line ends
        """
        for jump in self.soup.select("#jumps")[0].select(".j"):
            parts = jump["id"].split("-")
            if parts[0] == "j":
                start_system = self.systemsById[int(parts[1])]
                stop_system = self.systemsById[int(parts[2])]
                start_system.add_neighbour(stop_system)

    def _get_svg_from_dotlan(self, region):
        url = self.DOTLAN_BASIC_URL.format(region)
        content = requests.get(url).text
        return content

    def add_system_statistics(self, statistics):
        logging.info("add_system_statistics start")
        if statistics is not None:
            for systemId, system in self.systemsById.items():
                if systemId in statistics:
                    system.setStatistics(statistics[systemId])
        else:
            for system in self.systemsById.values():
                system.setStatistics(None)
        logging.info("add_system_statistics complete")

    def change_statistics_visibility(self):
        new_status = False if self._statisticsVisible else True
        value = "visible" if new_status else "hidden"
        for line in self.soup.select(".statistics"):
            line["visibility"] = value
        self._statisticsVisible = new_status
        return new_status

    def debug_write_soup(self):
        svg_data = self.soup.prettify("utf-8")
        try:
            with open("/Users/mark/Desktop/output.svg", "wb") as svgFile:
                svgFile.write(svg_data)
                svgFile.close()
        except Exception as e:
            logging.error(e)


class System(object):
    """
        A System on the Map
    """

    ALARM_COLORS = [(60 * 4, "#FF0000", "#FFFFFF"), (60 * 10, "#FF9B0F", "#FFFFFF"), (60 * 15, "#FFFA0F", "#000000"),
                    (60 * 25, "#FFFDA2", "#000000"), (60 * 60 * 24, "#FFFFFF", "#000000")]
    ALARM_COLOR = ALARM_COLORS[0][1]
    UNKNOWN_COLOR = "#FFFFFF"
    CLEAR_COLOR = "#59FF6C"

    def __init__(self, name, svg_element, map_soup, map_coordinates, transform, system_id):
        self.status = states.UNKNOWN
        self.name = name
        self.svgElement = svg_element
        self.mapSoup = map_soup
        self.origSvgElement = svg_element
        self.rect = svg_element.select("rect")[0]
        self.secondLine = svg_element.select("text")[1]
        self.lastAlarmTime = 0
        self.messages = []
        self.set_status(states.UNKNOWN)
        self.__locatedCharacters = []
        self.backgroundColor = "#FFFFFF"
        self.mapCoordinates = map_coordinates
        self.systemId = system_id
        self.transform = transform
        self.cachedOffsetPoint = None
        self._neighbours = set()
        self.statistics = {"jumps": "?", "shipkills": "?", "factionkills": "?", "podkills": "?"}

    def get_transform_offset_point(self):
        if not self.cachedOffsetPoint:
            if self.transform:
                # Convert data in the form 'transform(0,0)' to a list of two floats
                point_string = self.transform[9:].strip('()').split(',')
                self.cachedOffsetPoint = [float(point_string[0]), float(point_string[1])]
            else:
                self.cachedOffsetPoint = [0.0, 0.0]
        return self.cachedOffsetPoint

    def mark(self):
        marker = self.mapSoup.select("#select_marker")[0]
        offset_point = self.get_transform_offset_point()
        x = self.mapCoordinates["center_x"] + offset_point[0]
        y = self.mapCoordinates["center_y"] + offset_point[1]
        marker["transform"] = "translate({x},{y})".format(x=x, y=y)
        marker["opacity"] = "1"
        marker["activated"] = time.time()

    def add_located_character(self, charname):
        id_name = self.name + u"_loc"
        was_located = bool(self.__locatedCharacters)
        if charname not in self.__locatedCharacters:
            self.__locatedCharacters.append(charname)
        if not was_located:
            coords = self.mapCoordinates
            new_tag = self.mapSoup.new_tag("ellipse", cx=coords["center_x"] - 2.5, cy=coords["center_y"], id=id_name,
                                           rx=coords["width"] / 2 + 4, ry=coords["height"] / 2 + 4, style="fill:#8b008d",
                                           transform=self.transform)
            jumps = self.mapSoup.select("#jumps")[0]
            jumps.insert(0, new_tag)

    def set_background_color(self, color):
        for rect in self.svgElement("rect"):
            if "location" not in rect.get("class", []) and "marked" not in rect.get("class", []):
                rect["style"] = "fill: {0};".format(color)

    def get_located_characters(self):
        characters = []
        for char in self.__locatedCharacters:
            characters.append(char)
        return characters

    def remove_located_character(self, charname):
        id_name = self.name + u"_loc"

        if charname in self.__locatedCharacters:
            self.__locatedCharacters.remove(charname)
            if not self.__locatedCharacters:
                for element in self.mapSoup.select("#" + id_name):
                    element.decompose()

    def add_neighbour(self, neighbour_system):
        """
            Add a neigbour system to this system
            neighbour_system: a system (not a system's name!)
        """
        self._neighbours.add(neighbour_system)
        neighbour_system._neighbours.add(self)

    def get_neighbours(self, distance=1):
        """
            Get all neigboured system with a distance of distance.
            example: sys1 <-> sys2 <-> sys3 <-> sys4 <-> sys5
            sys3(distance=1) will find sys2, sys3, sys4
            sys3(distance=2) will find sys1, sys2, sys3, sys4, sys5
            returns a dictionary with the system (not the system's name!)
            as key and a dict as value. key "distance" contains the distance.
            example:
            {sys3: {"distance"}: 0, sys2: {"distance"}: 1}
        """
        systems = {self: {"distance": 0}}
        current_distance = 0
        while current_distance < distance:
            current_distance += 1
            new_systems = []
            for system in systems.keys():
                for neighbour in system._neighbours:
                    if neighbour not in systems:
                        new_systems.append(neighbour)
            for newSystem in new_systems:
                systems[newSystem] = {"distance": current_distance}
        return systems

    def remove_neighbour(self, system):
        """
            Removes the link between to neighboured systems
        """
        if system in self._neighbours:
            self._neighbours.remove(system)
        if self in system._neighbours:
            system._neigbours.remove(self)

    def set_status(self, new_status):
        if new_status == states.ALARM:
            self.lastAlarmTime = time.time()
            if "stopwatch" not in self.secondLine["class"]:
                self.secondLine["class"].append("stopwatch")
            self.secondLine["alarmtime"] = self.lastAlarmTime
            self.secondLine["style"] = "fill: #FFFFFF;"
            self.set_background_color(self.ALARM_COLOR)
        elif new_status == states.CLEAR:
            self.lastAlarmTime = time.time()
            self.set_background_color(self.CLEAR_COLOR)
            self.secondLine["alarmtime"] = 0
            if "stopwatch" not in self.secondLine["class"]:
                self.secondLine["class"].append("stopwatch")
            self.secondLine["alarmtime"] = self.lastAlarmTime
            self.secondLine["style"] = "fill: #000000;"
            self.secondLine.string = "clear"
        elif new_status == states.WAS_ALARMED:
            self.set_background_color(self.UNKNOWN_COLOR)
            self.secondLine["style"] = "fill: #000000;"
        elif new_status == states.UNKNOWN:
            self.set_background_color(self.UNKNOWN_COLOR)
            # second line in the rects is reserved for the clock
            self.secondLine.string = "?"
            self.secondLine["style"] = "fill: #000000;"
        if new_status not in (states.NOT_CHANGE, states.REQUEST):  # unknown not affect system status
            self.status = new_status

    def set_statistics(self, statistics):
        if statistics is None:
            text = "stats n/a"
        else:
            text = "j-{jumps} f-{factionkills} s-{shipkills} p-{podkills}".format(**statistics)
        svgtext = self.mapSoup.select("#stats_" + str(self.systemId))[0]
        svgtext.string = text

    def update(self):
        # state changed?
        if self.status == states.ALARM:
            alarm_time = time.time() - self.lastAlarmTime
            for maxDiff, alarmColor, secondLineColor in self.ALARM_COLORS:
                if alarm_time < maxDiff:
                    if self.backgroundColor != alarmColor:
                        self.backgroundColor = alarmColor
                        for rect in self.svgElement("rect"):
                            if "location" not in rect.get("class", []) and "marked" not in rect.get("class", []):
                                rect["style"] = "fill: {0};".format(self.backgroundColor)
                        self.secondLine["style"] = "fill: {0};".format(secondLineColor)
                    break
        if self.status in (states.ALARM, states.WAS_ALARMED, states.CLEAR):  # timer
            diff = math.floor(time.time() - self.lastAlarmTime)
            minutes = int(math.floor(diff / 60))
            seconds = int(diff - minutes * 60)
            string = "{m:02d}:{s:02d}".format(m=minutes, s=seconds)
            if self.status == states.CLEAR:
                seconds_until_white = 10 * 60
                calc_value = int(diff / (seconds_until_white / 255.0))
                if calc_value > 255:
                    calc_value = 255
                    self.secondLine["style"] = "fill: #008100;"
                string = "clr: {m:02d}:{s:02d}".format(m=minutes, s=seconds)
                self.set_background_color("rgb({r},{g},{b})".format(r=calc_value, g=255, b=calc_value))
            self.secondLine.string = string


def convert_region_name(name):
    """
        Converts a (system)name to the format that dotland uses
    """
    converted = []
    next_upper = False

    for index, char in enumerate(name):
        if index == 0:
            converted.append(char.upper())
        else:
            if char in (u" ", u"_"):
                char = "_"
                next_upper = True
            else:
                if next_upper:
                    char = char.upper()
                else:
                    char = char.lower()
                next_upper = False
            converted.append(char)
    return u"".join(converted)


# this is for testing:
if __name__ == "__main__":
    map = Map("Providence", "Providence.svg")
    s = map.systems["I7S-1S"]
    s.set_status(states.ALARM)
    logging.error(map.svg)
