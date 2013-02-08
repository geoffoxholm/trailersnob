import sys, os
import re
import json
import urllib2
from xbmcswift2 import Plugin, xbmc, xbmcaddon
import xbmcvfs
from lib import scraper

"""
TODO:
1. Make (cached) function to get movie details
2. Incorporate that info into the "play trailer" if possible
3. Try to download
4. Make script entrypoint

"""

DO_FOR_ALL = "**DO_::FOR::_ALL**" # An invalid movie name sentinel

plugin = Plugin()

# Calls XBMC's JSON RPC
def send_request(method, params = None):
    HEADERS = {'content-type' : 'application/json'}
    data = {"method"  : method,
            "jsonrpc" : "2.0",
            "id"      : plugin.id}
    if params is not None:
        data["params"] = params
    return eval(xbmc.executeJSONRPC( json.dumps(data) ))


# Makes a movie title into an HD-Trailer's title
def clean(title):
    return title.replace(" ", "-").lower()

# HACK! Modify the HD Trailers.net scraper to follow redirects
get_tree_original = scraper.__get_tree
@plugin.cached()
def get_tree_new(url, tries = 0):
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
# END HACK

##
## -- Beginning of URL handling functions --
##

@plugin.route('/')
def root_menu():
    items = [{'label':"All movies",
              'path': plugin.url_for('all_menu', filter_by = "None")},
             {'label':"Movies with no trailer",
              'path': plugin.url_for('all_menu', filter_by = "empty")},
             {'label':"Movies with missing trailers",
              'path': plugin.url_for('all_menu', filter_by = "404")},
             {'label':"Movies with low-resolution trailers",
              'path': plugin.url_for('all_menu', filter_by = "lame")}]
    return items

def trailer_exists(url):
    if xbmcvfs.exists(url):
        return True
    try:
        urllib2.urlopen(url)
        return True
    except:
        return False


title_preferences = ['theatrical trailer', 'trailer', 'trailer mirror', 'trailer no. 1', 'trailer no. 2', '^.* full trailer$']
def trailer_title_rank(title):
    lc = title.lower()
    for (candidate, rank) in zip(title_preferences, range(len(title_preferences))):
        if re.match(candidate, lc):
            return rank
    return -1


def good_title(title):
    return title.lower() in ["theatrical trailer", "trailer"]

def get_all_movie_ids(filter_by):
    movies = get_movies(filter_by)
    return [movie["movieid"] for movie in movies]

def get_movies(filter_by):
    if filter_by == "None":
        fxn = lambda x : True
    elif filter_by == "empty":
        fxn = lambda x : get_details(x["movieid"])["trailer"] == ""
    elif filter_by == "404":
        fxn = lambda x : not trailer_exists(get_details(x["movieid"])["trailer"])

    movies = send_request("VideoLibrary.GetMovies")["result"]["movies"]
    return filter(fxn, movies)


@plugin.route('/movies/<filter_by>')
def all_menu(filter_by):
    movies = get_movies(filter_by)
    items = [{'label' : "Do for all",
              'path'  : plugin.url_for('movie_menu',
                                       movie_id = "%s|%s" %(DO_FOR_ALL, filter_by))}]
    for movie in movies:
        items.append( {'label': movie["label"],
                       'path' : plugin.url_for('movie_menu',
                                               movie_id = "%d" % movie["movieid"])} )
    return items

def get_details(movie_id):
    result = send_request("VideoLibrary.GetMovieDetails",
                          {"properties" : ["trailer", "year"], "movieid" : int(movie_id)})
    return result["result"]["moviedetails"]

@plugin.route('/movie/<movie_id>')
def movie_menu(movie_id):
    items = [{'label' : "Clear trailer",
              'path'  : plugin.url_for('set_trailer',
                                       movie_id = movie_id,
                                       url  = "None",
                                       source = "None",
                                       return_to = "movie_menu")},
             {'label' : "Set to best guess",
              'path'  : plugin.url_for('set_best_guess_trailer',
                                       movie_id = movie_id)}]
    if not movie_id.startswith(DO_FOR_ALL):
        details = get_details(movie_id)
        if trailer_exists(details["trailer"]):
            items.append({'label' : "Play current trailer",
                          'is_playable' : True,
                          'path'  : plugin.url_for('play_trailer', movie_id = movie_id)})
        items.append({'label' : "Choose trailer",
                      'path'  : plugin.url_for('trailer_menu', movie_id = movie_id)})

    return items

@plugin.route('/movie/<movie_id>/set_trailer/guess')
def set_best_guess_trailer(movie_id):
    batch = False
    if movie_id.startswith(DO_FOR_ALL):
        batch = True
        movie_ids = get_all_movie_ids(movie_id.split("|")[1])
    else:
        movie_ids = [movie_id]

    succeeded = 0
    for the_movie_id in movie_ids:
        details = get_details(int(the_movie_id))
        try:
            movie, trailers, clips = scraper.get_videos(clean(details["label"]))
        except scraper.NetworkError:
            if not batch:
                plugin.notify("No trailers found.")
            continue

        resolution = plugin.get_setting("resolution")
        resolutions = ["1080p", "720p", "480p"]
        resolutions.remove(resolution)
        resolutions.insert(0, resolution)
        for resolution in resolutions:
            best_rank  = -1
            best_index = None
            for (trailer, index) in zip(trailers, range(len(trailers))):
                if resolution in trailer["resolutions"]:
                    rank = trailer_title_rank(trailer["title"])
                    if rank >= 0 and (rank < best_rank or best_index is None):
                        best_rank  = rank
                        best_index = index

            if best_index is not None:
                trailer = trailers[best_index]
                if not batch or len(movie_ids) == 1:
                    plugin.notify("Found %s trailer: \"%s\"" % (resolution, trailer["title"]))
                plugin.log.info("Found %s trailer: \"%s\"" % (resolution, trailer["title"]))
                do_set_trailer(the_movie_id, trailer["resolutions"][resolution], trailer["source"])
                succeeded += 1
                break

    if batch and len(movie_ids) > 1:
        plugin.notify("Found %d/%d trailers for you." % (succeeded, len(movie_ids)))
    else:
        if batch and not succeeded:
            plugin.notify("Could not find good trailers for you.")
    return plugin.finish(movie_menu(movie_id), update_listing = True)


@plugin.route('/movie/<movie_id>/play')
def play_trailer(movie_id):
    details = get_details(movie_id)
    trailer = details["trailer"]
    plugin.log.info("Playing: %s" % trailer)
    plugin.set_resolved_url(trailer)

@plugin.route('/movie/<movie_id>/list')
def trailer_menu(movie_id):
    details = get_details(int(movie_id))
    try:
        movie, trailers, clips = scraper.get_videos(clean(details["label"]))
    except scraper.NetworkError:
        plugin.notify("No trailers found.")
        return None
    currentTrailer = details["trailer"].split("|")[0]
    resolution = plugin.get_setting("resolution")
    items = []
    for trailer in trailers:
        if resolution in trailer["resolutions"]:
            url = trailer['resolutions'][resolution]
            item = {'label' : trailer["title"],
                    'path'  : plugin.url_for('set_trailer',
                                             movie_id = movie_id, url = url,
                                             source = trailer['source'],
                                             return_to = "trailer_menu")}
            if url == currentTrailer:
                item["label"] = "CURRENT: %s " % item["label"]
                items.insert(0, item)
            else:
                items.append(item)
    return items

def do_set_trailer(movie_id, url, source):
    if source == "apple.com":
        url = '%s|User-Agent=QuickTime' % url

    details = get_details(int(movie_id))
    if details["trailer"] != url:
        return send_request('VideoLibrary.SetMovieDetails', {'movieid' : int(movie_id), 'trailer' : url})
    return {"result" : "OK"}


@plugin.route('/movie/<movie_id>/set_trailer/<url>/<source>/<return_to>')
def set_trailer(movie_id, url, source, return_to):
    if url == "None":
        url = ""
        source = ""

    batch = False
    if movie_id.startswith(DO_FOR_ALL):
        movie_ids = get_all_movie_ids(movie_id.split("|")[1])
        batch = True
    else:
        movie_ids = [movie_id]

    for the_movie_id in movie_ids:
        result = do_set_trailer(the_movie_id, url, source)
        if "result" in result:
            if result["result"] == "OK":
                if not batch:
                    plugin.notify("Successfully set trailer")
                plugin.log.info("Set trailer for \"%s\" to: %s" % (the_movie_id, url))
            else:
                plugin.log.info("result: %s" % result)
        else:
            plugin.log.error("result: %s" % result)


    if return_to == "trailer_menu":
        return plugin.finish(trailer_menu(movie_id), update_listing = True)
    elif return_to == "movie_menu":
        return plugin.finish(movie_menu(movie_id), update_listing = True)


if __name__ == "__main__":
    try:
        plugin.run()
    except IOError as e:
        plugin.log.error(e)
