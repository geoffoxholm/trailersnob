import sys, os
import xbmc, xbmcgui, xbmcaddon, xbmcplugin
import unicodedata
import urllib
import re
import json

import datetime

#from lib import scraper

from lib import scraper

__addonid__ =     'plugin.video.trailerupdater'
__addon__ =       xbmcaddon.Addon(id=__addonid__)
__addonname__ =   __addon__.getAddonInfo('name')
__scriptdebug__ = True
__handle__ =      int(sys.argv[1])


def sendRequest(method, params = None):
    HEADERS = {'content-type' : 'application/json'}
    data = {"method"  : method,
            "jsonrpc" : "2.0",
            "id"      : __addonid__}
    if params is not None:
        data["params"] = params

    return eval(xbmc.executeJSONRPC( json.dumps(data) ))

def tryURL(url):
    tree = scraper.__get_tree(url)
    result = tree.find("meta", attrs = {"http-equiv":"refresh"})
    if result:
        wait,text=result["content"].split(";")
        if text.lower().startswith("url="):
            url=text[4:]
            return url
    return url

def clean(title):
    return title.replace(" ", "-").lower()
    # movie_id = title.replace(" ", "-").lower() + "/"
    # url = scraper.MAIN_URL + 'movie/%s' % movie_id
    # url = tryURL(url)
    # return os.path.basename(os.path.dirname(url))

get_tree_original = scraper.__get_tree

def get_tree_new(url, tries = 0):
    print "__get_tree(%s)" % url

    if tries > 2:
        return None

    tree = get_tree_original(url)
    result = tree.find("meta", attrs = {"http-equiv":"refresh"})
    if result:
        wait,text=result["content"].split(";")
        if text.lower().startswith("url="):
            url=text[4:]
            return get_tree_new(url, tries + 1)
    else:
        return tree

def log(message):
    xbmc.log("%s: %s" % (__addonid__, message))

scraper.__get_tree = get_tree_new

movies = sendRequest("VideoLibrary.GetMovies")["result"]["movies"]

resolutions = ["480p", "720p", "1080p"]
resolution = resolutions[int(__addon__.getSetting("resolution"))]


log("Preferred resolution: %s" % resolution)


movie, trailers, clips = scraper.get_videos(clean(movies[0]["label"]))

for trailer in trailers:
    if trailer["title"] == "Theatrical Trailer":
        url = trailer['resolutions'][resolution]
        log(url)

