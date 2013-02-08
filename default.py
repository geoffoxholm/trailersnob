import sys, os
import re
import json
from xbmcswift2 import Plugin, xbmc, xbmcaddon
from lib import scraper

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
    items = [
        {'label':"All Movies",
         'path': plugin.url_for('all_menu', filter_by = "None")}
        ]
    return items

def list_movies(movies, filter_by):
    items = []
    for movie in movies:
        items.append( {'label': movie["label"],
                       'path' : plugin.url_for('movie_menu',
                                               movie_id = "%d" % movie["movieid"],
                                               filter_by = filter_by)} )
    return items


@plugin.route('/movies/<filter_by>')
def all_menu(filter_by):
    return list_movies(send_request("VideoLibrary.GetMovies")["result"]["movies"], filter_by)

def get_details(movie_id):
    result = send_request("VideoLibrary.GetMovieDetails",
                          {"properties" : ["trailer", "year"], "movieid" : int(movie_id)})
    return result["result"]["moviedetails"]

@plugin.route('/movies/<filter_by>/<movie_id>')
def movie_menu(filter_by, movie_id):
    details = get_details(movie_id)
    items = [{'label' : "Play current trailer",
              'is_playable' : True,
              'path'  : plugin.url_for('play_trailer',
                                       movie_id = movie_id,
                                       filter_by = filter_by)},
             {'label' : "Choose trailer",
              'path'  : plugin.url_for('trailer_menu',
                                       movie_id = movie_id,
                                       filter_by = filter_by) } ]
    return items

@plugin.route('/movies/<filter_by>/<movie_id>/play')
def play_trailer(filter_by, movie_id):
    details = get_details(movie_id)
    trailer = details["trailer"]
    plugin.log.info("Playing: %s" % trailer)
    plugin.set_resolved_url(trailer)

def trailer_menu_items(filter_by, movie_id):
    details = get_details(int(movie_id))
    try:
        movie, trailers, clips = scraper.get_videos(clean(details["label"]))
    except scraper.NetworkError:
        plugin.notify("No trailers found.")
        return None

    resolution = plugin.get_setting("resolution")
    items = []
    for trailer in trailers:
        if resolution in trailer["resolutions"]:
            items.append({'label' : trailer["title"],
                          'path'  : plugin.url_for('set_trailer',
                                                   filter_by = filter_by, movie_id = movie_id,
                                                   url = trailer['resolutions'][resolution],
                                                   source = trailer['source'])})
    return items

@plugin.route('/movies/<filter_by>/<movie_id>/list')
def trailer_menu(filter_by, movie_id):
    return trailer_menu_items(filter_by, movie_id)


@plugin.route('/movies/<filter_by>/<movie_id>/set_trailer/<url>/<source>')
def set_trailer(filter_by, movie_id, url, source):
    if source == "apple.com":
        url = '%s|User-Agent=QuickTime' % url

    result = send_request('VideoLibrary.SetMovieDetails',
                          {'movieid' : int(movie_id), 'trailer' : url})
    if "result" in result:
        if result["result"] == "OK":
            plugin.notify(msg='Successfully set trailer')
            plugin.log.info("Set trailer for \"%s\" to: %s" % (movie_id, url))
        else:
            plugin.log.error("Failed to set trailer for \"%s\" to: %s" % (movie_id, url))
            plugin.log.error(result)
    else:
        plugin.log.error(result["error"])

    # Go back to trailer menu
    return plugin.finish(trailer_menu_items(filter_by, movie_id), update_listing = True)

if __name__ == "__main__":
    plugin.run()
