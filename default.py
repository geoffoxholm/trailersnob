import sys, os
import xbmc, xbmcgui, xbmcaddon, xbmcplugin
import unicodedata
import urllib
from urlparse import parse_qs
import re
import json
from xbmcswift2 import Plugin
import datetime

#from lib import scraper

from lib import scraper

__addonid__ =     'plugin.video.trailersnob'
__addon__ =       xbmcaddon.Addon(id=__addonid__)
__addonname__ =   __addon__.getAddonInfo('name')
__scriptdebug__ = True
__handle__ =      int(sys.argv[1])

def enum(*sequential, **named):
    enums = dict(zip(sequential, range(len(sequential))), **named)
    return type('Enum', (), enums)

TASKS = enum('ALL', 'MISSING', 'BAD', 'LAME', 'SHOW_MOVIE')
TASK = "task"
MOVIE_ID = "movieid"

plugin = Plugin()


def send_request(method, params = None):
    HEADERS = {'content-type' : 'application/json'}
    data = {"method"  : method,
            "jsonrpc" : "2.0",
            "id"      : __addonid__}
    if params is not None:
        data["params"] = params

    print json.dumps(data)

    return eval(xbmc.executeJSONRPC( json.dumps(data) ))


def clean(title):
    return title.replace(" ", "-").lower()

# Modify the HD Trailers.net scraper to follow redirects
get_tree_original = scraper.__get_tree
@plugin.cached()
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
scraper.__get_tree = get_tree_new

@plugin.route('/')
def root_menu():
    items = [
        {'label':"All Movies",
         'path': plugin.url_for('all_menu', filter_by = "None")}
        ]
    return plugin.finish(items)

def list_movies(movies, filter_by):
    items = []
    for movie in movies:
        items.append( {'label': movie["label"],
                       'path' : plugin.url_for('movie_menu',
                                               movie_id = "%d" % movie[MOVIE_ID],
                                               filter_by = filter_by)} )
        print movie[MOVIE_ID]
    return plugin.finish(items)

@plugin.route('/movies/<filter_by>')
def all_menu(filter_by):
    list_movies(send_request("VideoLibrary.GetMovies")["result"]["movies"], filter_by)

def get_details(movie_id):
    result = send_request("VideoLibrary.GetMovieDetails", {"properties" : ["trailer", "year"], "movieid" : int(movie_id)})
    return result["result"]["moviedetails"]

@plugin.route('/movies/<filter_by>/<movie_id>')
def movie_menu(filter_by, movie_id):
    details = get_details(movie_id)
    items = [
        {'label' : "Play current trailer",
         'path'  : plugin.url_for('play_trailer',
                                  movie_id = movie_id,
                                  filter_by = filter_by),
         'is_playable' : True},
         {'label' : "Choose trailer",
         'path'  : plugin.url_for('trailer_menu',
                                  movie_id = movie_id,
                                  filter_by = filter_by) }
        ]
    return plugin.finish(items)

@plugin.route('/movies/<filter_by>/<movie_id>/play')
def play_trailer(filter_by, movie_id):
    details = get_details(movie_id)
    trailer = details["trailer"]
    plugin.log.info("Playing: %s" % trailer)
    plugin.set_resolved_url(trailer)

@plugin.route('/movies/<filter_by>/<movie_id>/list')
def trailer_menu(filter_by, movie_id):
    details = get_details(int(movie_id))
    try:
        movie, trailers, clips = scraper.get_videos(clean(details["label"]))
    except scraper.NetworkError:
        plugin.notify("No trailers found.")
        return None

    resolution = __addon__.getSetting("resolution")
    items = []
    for trailer in trailers:
        if resolution in trailer["resolutions"]:
            items.append(
            {'label' : trailer["title"],
             'path'  : plugin.url_for('set_trailer', filter_by = filter_by, url = trailer['resolutions'][resolution], movie_id = movie_id, source = trailer['source'])})
    return plugin.finish(items)

@plugin.route('/movies/<filter_by>/<movie_id>/set_trailer/<url>/<source>')
def set_trailer(filter_by, movie_id, url, source):
    if source == "apple.com":
        url = '%s|User-Agent=QuickTime' % url

    result = send_request('VideoLibrary.SetMovieDetails', {'movieid' : int(movie_id), 'trailer' : url})
    if "result" in result:
        if result["result"] == "OK":
            plugin.notify(msg='Successfully set trailer')
            plugin.log.info("Set trailer for \"%s\" to: %s" % (movie_id, url))
        else:
            plugin.log.error("Failed to set trailer for \"%s\" to: %s" % (movie_id, url))
            plugin.log.error(result)
    else:
        plugin.log.error(result["error"])

    #plugin.set_resolved_url(plugin.url_for('trailer_menu', filter_by = filter_by, movie_id = movie_id))
    # plugin.finish(succeeded=False, update_listing = False

    return None










if __name__ == "__main__":
    # try:
        plugin.run()
    # except scraper.NetworkError:
        # plugin.notify(msg="Network Error"))



    # if not sys.argv[2]:
    #     log("Started")
    #     root_menu()
    # else:
    #     args = parse_qs(sys.argv[2][1:])
    #     task = int(args[TASK][0])
    #     log(args)
    #     if TASKS.ALL == task:
    #         all_menu()
    #     elif TASKS.SHOW_MOVIE == task:
    #         movie_menu(int(args[MOVIE_ID]))


#

# movies = send_request("VideoLibrary.GetMovies")["result"]["movies"]

# #resolutions = ["480p", "720p", "1080p"]
# resolution = __addon__.getSetting("resolution")


# log("Preferred resolution: %s" % resolution)


# movie, trailers, clips = scraper.get_videos(clean(movies[0]["label"]))

# for trailer in trailers:
#     if trailer["title"] == "Theatrical Trailer":
#         url = trailer['resolutions'][resolution]
#         log(url)

