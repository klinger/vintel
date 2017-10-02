
<p align="center">
  <img align="middle" src="src/vi/ui/res/logo.png">
</p>
# Welcome To Vintel Recon Citadels



Vintel Recon is a modification of "Vintel" (Visual intel chat analysis), a planning and notification application for [EVE Online](http://www.eveonline.com). Gathers status through in-game intelligence channels on all known hostiles and presents all the data on a [dotlan](http://evemaps.dotlan.net/map/Cache#npc24) generated regional map. The map is annotated in real-time as players report intel in monitored chat channels.

Vintel is written with Python 2.7, using PyQt4 for the application presentation layer, BeautifulSoup4 for SVG parsing.

### News
_The current release version of Vintel Recon [can be found here](https://)._

Keep up on the latest at the [wiki](https://) or visit our [issues](https://github.com/) page to see what bugs and features are in the queue.


## Features

 - Platforms supported: Windows and Linux.
 - Systems on the map display different color backgrounds as theier need for recon (red->orange->yellow->white) 
 - Clicking on a specific system will display all citadels and engineering complexes in that system. 
 - The system where your character is currently located is highlighted on the map with an violet background automatically whenever a characater changes systems.
 - The main window can be set up to remain "always on top" and be displayed with a specified level of transparency.
 
## Usage

## Running Vintel from Source

To run or build from the source you need the following packages installed on your machine. Most, if not all, can be installed from the command line using package management software such as "pip". Mac and Linux both come with pip installed, Windows users may need to install [cygwin](https://www.cygwin.com) to get pip. Of course all the requirements also have downoad links.

The packages required are:
- Python 2.7.x
https://www.python.org/downloads/
Vintel is not compatible with Python 3!
- PyQt4x
http://www.riverbankcomputing.com/software/pyqt/download
Please use the PyQt Binary Package for Py2.7
Vintel is not compatible with PyQt5!
- BeautifulSoup 4
https://pypi.python.org/pypi/beautifulsoup4 for debian install the bt4 package too.
- Requests 2
https://pypi.python.org/pypi/requests
- Six for python 3 compatibility https://pypi.python.org/pypi/six

## Building the Vintel Standalone Package

 - The standalone is created using pyinstaller. All media files and the .spec-file with the configuration for pyinstaller are included in the source repo. Pyinstaller can be found here: https://github.com/pyinstaller/pyinstaller/wiki.
 - Edit the .spec file to match your src path in the "a = Analysis" section and execute "pyinstaller vintel.spec vintel.py". If everything went correctly you should get a dist folder that contains the standalone executable.

## FAQ

**License?**

Vintel is licensed under the [GPLv3](http://www.gnu.org/licenses/gpl-3.0.html).

**A litte bit to big for such a little tool.**

The .exe ships with the complete environment and needed libs. You could save some space using the the source code instead.

**What file system permissions does Vintel need?**

- It reads your EVE chatlogs
- It creates and writes to **path-to-your-chatlogs**/../../vintel/.
- It needs to connect the internet (dotlan.evemaps.net, eveonline.com, cva-eve.org, and eve gate).

**Vintel calls home?**

Yes it does. If you don't want to this, use a firewall to forbid it.
Vintel looks for a new version at startup and loads dynamic infomation (i.e., jump bridge routes) from home. It will run without this connection but some functionality will be limited.

**Vintel does not find my chatlogs or is not showing changes to chat when it should. What can I do?**

Vintel looks for your chat logs in ~\EVE\logs\chatlogs and ~\DOCUMENTS\EVE\logs\chatlogs. Logging must be enabled in the EVE client options. You can set this path on your own by giving it to Vintel at startup. For this you have to start it on the command line and call the program with the path to the logs.

Examples:

`win> vintel-1.0.exe "d:\strange\path\EVE\logs\chatlogs"`

    – or –

`linux and mac> python vintel.py "/home/user/myverypecialpath/EVE/logs/chatlogs"`

**Vintel does not start! What can I do?**

Please try to delete Vintel's Cache. It is located in the EVE-directory where the chatlogs are in. If your chatlogs are in \Documents\EVE\logs\chatlogs Vintel writes the cachte to \Documents\EVE\vintel

**Vintel takes many seconds to start up; what are some of the causes and what can I do about it?**

Vintel asks the operating system to notifiy when a change has been made to the ChatLogs directory - this will happen when a new log is created or an existing one is updated. In response to this notification, Vintel examines all of the files in the directory to analysze the changes. If you have a lot of chat logs this can make Vintel slow to scan for file changes. Try perodically moving all the chatlogs out of the ChatLogs directory (zip them up and save them somewhere else if you think you may need them some day).

**Vintel complains about missing dll files on Windows at app launch, is there a workaround for this?**

Yes there is! There is a bit of a mix up going on with the latest pyinstaller and the Microsoft developer dlls. Here is a link to help illuminate the issue https://github.com/pyinstaller/pyinstaller/issues/1974

You can visit Microsoft's web site to download the developer dlls https://www.microsoft.com/en-in/download/details.aspx?id=5555.

You can also read a more technical treatment of the issue here http://www.tomshardware.com/answers/id-2417960/msvcr100-dll-32bit-64bit.html

**How can I resolve the "empty certificate data" error?**

Do not use the standalone EXE, install the environment and use the sourcecode directly. There are missing certificates that must be provided by the environment. This error was discovered when running the standalone EXE on Linux using wine.

**Vintel is misbehaving and I dont know why - how can I easily help diagnose problems with Vintel**

Vintel writes its own set of logs to the \Documents\EVE\vintel\vintel directory. A new log is created as the old one fills up to its maximum size setting. Each entry inside the log file is time-stamped. These logs are emitted in real-time so you can watch the changes to the file as you use the app.