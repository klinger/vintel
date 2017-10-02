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

import logging
import sqlite3
import threading
import time

import six

from dbstructure import update_database

if six.PY2:
    def to_blob(x):
        return buffer(str(x))


    def from_blob(x):
        return str(x[0][0])
else:
    def to_blob(x):
        return x


    def from_blob(x):
        return x


class Cache(object):
    # Cache checks PATH_TO_CACHE when init, so you can set this on a
    # central place for all Cache instances.
    PATH_TO_CACHE = None

    # Ok, this is dirty. To make sure we check the database only
    # one time/runtime we will change this classvariable after the
    # check. Following inits of Cache will now, that we allready checked.
    VERSION_CHECKED = False

    # Cache-Instances in various threads: must handle concurrent writings
    SQLITE_WRITE_LOCK = threading.Lock()

    def __init__(self, path_to_sqlite_file="cache.sqlite3"):
        """ pathToSQLiteFile=path to sqlite-file to save the cache. will be ignored if you set Cache.PATH_TO_CACHE before init
        """
        if Cache.PATH_TO_CACHE:
            path_to_sqlite_file = Cache.PATH_TO_CACHE
        self.con = sqlite3.connect(path_to_sqlite_file)
        if not Cache.VERSION_CHECKED:
            with Cache.SQLITE_WRITE_LOCK:
                self.check_version()
        Cache.VERSION_CHECKED = True

    def check_version(self):
        query = "SELECT version FROM version;"
        version = 0
        try:
            version = self.con.execute(query).fetchall()[0][0]
        except Exception as e:
            if isinstance(e, sqlite3.OperationalError) and "no such table: version" in str(e):
                pass
            elif isinstance(e, IndexError):
                pass
            else:
                raise e
        update_database(version, self.con)

    def put_into_cache(self, key, value, max_age=60 * 60 * 24 * 3):
        """ Putting something in the cache maxAge is maximum age in seconds
        """
        with Cache.SQLITE_WRITE_LOCK:
            query = "DELETE FROM cache WHERE key = ?"
            self.con.execute(query, (key,))
            query = "INSERT INTO cache (key, data, modified, maxAge) VALUES (?, ?, ?, ?)"
            self.con.execute(query, (key, value, time.time(), max_age))
            self.con.commit()

    def get_fromcache(self, key, outdated=False):
        """ Getting a value from cache
            key = the key for the value
            outdated = returns the value also if it is outdated
        """
        query = "SELECT key, data, modified, maxage FROM cache WHERE key = ?"
        founds = self.con.execute(query, (key,)).fetchall()
        if len(founds) == 0:
            return None
        elif founds[0][2] + founds[0][3] < time.time() and not outdated:
            return None
        else:
            return founds[0][1]

    def recall_and_apply_settings(self, responder, settings_identifier):
        settings = self.get_fromcache(settings_identifier)
        if settings:
            settings = eval(settings)
            for setting in settings:
                obj = responder if not setting[0] else getattr(responder, setting[0])
                # logging.debug("{0} | {1} | {2}".format(str(obj), setting[1], setting[2]))
                try:
                    getattr(obj, setting[1])(setting[2])
                except Exception as e:
                    logging.error(e)
