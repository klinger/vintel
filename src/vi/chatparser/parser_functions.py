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

""" 12.02.2015
	I know this is a little bit dirty, but I prefer to have all the functions
	to parse the chat in this file together.
	Wer are now work directly with the html-formatted text, which we use to
	display it. We are using a HTML/XML-Parser to have the benefit, that we
	can only work and analyze those text, that is still not on tags, because
	all the text in tags was allready identified.
	f.e. the ship_parser:
		we call it from the chatparser and give them the rtext (richtext).
		if the parser hits a shipname, it will modifiy the tree by creating
		a new tag and replace the old text with it (calls tet_replace),
		than it returns True.
		The chatparser will call the function again until it return False
		(None is False) otherwise.
		We have to call the parser again after a hit, because a hit will change
		the tree and so the original generator is not longer stable.
"""

import six

import vi.evegate as evegate
from bs4 import BeautifulSoup
from bs4.element import NavigableString
from vi import states

CHARS_TO_IGNORE = ("*", "?", ",", "!", ".")


def text_replace(element, new_text):
    new_text = "<t>" + new_text + "</t>"
    new_elements = []
    for newPart in BeautifulSoup(new_text, 'html.parser').select("t")[0].contents:
        new_elements.append(newPart)
    for newElement in new_elements:
        element.insert_before(newElement)
    element.replace_with(six.text_type(""))


def parse_status(rtext):
    texts = [t for t in rtext.contents if isinstance(t, NavigableString)]
    for text in texts:
        upper_text = text.strip().upper()
        original_text = upper_text
        for char in CHARS_TO_IGNORE:
            upper_text = upper_text.replace(char, "")
        upper_words = upper_text.split()
        if ("CLEAR" in upper_words or "CLR" in upper_words) and not original_text.endswith("?"):
            return states.CLEAR
        elif "STAT" in upper_words or "STATUS" in upper_words:
            return states.REQUEST
        elif "?" in original_text:
            return states.REQUEST
        elif text.strip().upper() in ("BLUE", "BLUES ONLY", "ONLY BLUE" "STILL BLUE", "ALL BLUES"):
            return states.CLEAR


def parse_ships(rtext):
    def format_ship_name(text, word):
        new_text = u"""<span style="color:#d95911;font-weight:bold"> {0}</span>"""
        text = text.replace(word, new_text.format(word))
        return text

    texts = [t for t in rtext.contents if isinstance(t, NavigableString)]
    for text in texts:
        upper_text = text.upper()
        for shipName in evegate.SHIPNAMES:
            if shipName in upper_text:
                hit = True
                start = upper_text.find(shipName)
                end = start + len(shipName)
                if ((start > 0 and upper_text[start - 1] not in (" ", "X")) or (
                                end < len(upper_text) - 1 and upper_text[end] not in ("S", " "))):
                    hit = False
                if hit:
                    ship_in_text = text[start:end]
                    formatted = format_ship_name(text, ship_in_text)
                    text_replace(text, formatted)
                    return True


def parse_systems(systems, rtext, found_systems):
    system_names = systems.keys()

    # words to ignore on the system parser. use UPPER CASE
    words_to_ignore = ("IN", "IS", "AS")

    def format_system(text, word, system):
        new_text = u"""<a style="color:#CC8800;font-weight:bold" href="mark_system/{0}">{1}</a>"""
        text = text.replace(word, new_text.format(system, word))
        return text

    texts = [t for t in rtext.contents if isinstance(t, NavigableString) and len(t)]
    for wtIdx, text in enumerate(texts):
        worktext = text
        for char in CHARS_TO_IGNORE:
            worktext = worktext.replace(char, "")

        # Drop redundant whitespace so as to not throw off word index
        worktext = ' '.join(worktext.split())
        words = worktext.split(" ")

        for idx, word in enumerate(words):

            # Is this about another a system's gate?
            if len(words) > idx + 1:
                if words[idx + 1].upper() == 'GATE':
                    bailout = True
                    if len(words) > idx + 2:
                        if words[idx + 2].upper() == 'TO':
                            # Could be '___ GATE TO somewhere' so check this one.
                            bailout = False
                    if bailout:
                        # '_____ GATE' mentioned in message, which is not what we're
                        # interested in, so go to checking next word.
                        continue

            upper_word = word.upper()
            if upper_word != word and upper_word in words_to_ignore: continue
            if upper_word in system_names:  # - direct hit on name
                found_systems.add(systems[upper_word])  # of the system?
                formatted_text = format_system(text, word, upper_word)
                text_replace(text, formatted_text)
                return True
            elif 1 < len(upper_word) < 5:  # - upperWord < 4 chars.
                for system in system_names:  # system begins with?
                    if system.startswith(upper_word):
                        found_systems.add(systems[system])
                        formatted_text = format_system(text, word, system)
                        text_replace(text, formatted_text)
                        return True
            elif "-" in upper_word and len(upper_word) > 2:  # - short with - (minus)
                upper_word_parts = upper_word.split("-")  # (I-I will match I43-IF3)
                for system in system_names:
                    system_parts = system.split("-")
                    if (len(upper_word_parts) == 2 and len(system_parts) == 2 and len(upper_word_parts[0]) > 1 and len(
                            upper_word_parts[1]) > 1 and len(system_parts[0]) > 1 and len(system_parts[1]) > 1 and len(
                        upper_word_parts) == len(system_parts) and upper_word_parts[0][0] == system_parts[0][0] and
                                upper_word_parts[1][0] == system_parts[1][0]):
                        found_systems.add(systems[system])
                        formatted_text = format_system(text, word, system)
                        text_replace(text, formatted_text)
                        return True
            elif len(upper_word) > 1:  # what if F-YH58 is named FY?
                for system in system_names:
                    cleared_system = system.replace("-", "")
                    if cleared_system.startswith(upper_word):
                        found_systems.add(systems[system])
                        formatted_text = format_system(text, word, system)
                        text_replace(text, formatted_text)
                        return True

    return False


def parse_urls(rtext):
    def find_urls(s):
        # yes, this is faster than regex and less complex to read
        urls = []
        prefixes = ("http://", "https://")
        for prefix in prefixes:
            start = 0
            while start >= 0:
                start = s.find(prefix, start)
                if start >= 0:
                    stop = s.find(" ", start)
                    if stop < 0:
                        stop = len(s)
                    urls.append(s[start:stop])
                    start += 1
        return urls

    def format_url(text, url):
        new_text = u"""<a style="color:#28a5ed;font-weight:bold" href="link/{0}">{0}</a>"""
        text = text.replace(url, new_text.format(url))
        return text

    texts = [t for t in rtext.contents if isinstance(t, NavigableString)]
    for text in texts:
        urls = find_urls(text)
        for url in urls:
            text_replace(text, format_url(text, url))
            return True
