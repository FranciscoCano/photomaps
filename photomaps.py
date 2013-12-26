#!/usr/bin/env python
import time
import sys
import os
import logging.config
from urllib2 import Request
import urllib2
import urllib
import math
from argparse import ArgumentParser
from ConfigParser import ConfigParser
from PIL import Image
from PIL.ExifTags import TAGS
import ImageFile
from dist import Point, VincentyDistance
import json


mean_radius=6371008.7714
max_width = mean_radius * 2 * math.pi * 2.5


def get_exif(fn):
    ret = {}
    i = Image.open(fn)
    info = i._getexif()
    for tag, value in info.items():
        decoded = TAGS.get(tag, tag)
        ret[decoded] = value
    return ret


def get_point_from_exif(image, exif_info):
    if 'GPSInfo' in exif_info:
        lat = exif_info['GPSInfo'][2]
        deg = float(lat[0][0]/lat[0][1])
        mins = float(lat[1][0]/lat[1][1])
        sec = float(lat[1][0]%lat[1][1]) * 0.6
        gpsmin = mins + sec/60
        wgsmin = gpsmin/60
        latitude = deg+wgsmin
        if exif_info['GPSInfo'][1] == 'S':
            latitude = -latitude
        lng = exif_info['GPSInfo'][4]
        deg = float(lng[0][0]/lng[0][1])
        mins = float(lng[1][0]/lng[1][1])
        sec = float(lng[1][0]%lng[1][1]) * 0.6
        gpsmin = mins + sec/60
        wgsmin = gpsmin/60
        longitude = deg+wgsmin
        if exif_info['GPSInfo'][3] == 'W':
            longitude = -longitude
        # print "{0} - WGS84 : {1:2.6f},{2:2.6f}".format(image, latitude, longitude)
        p = Point(latitude, longitude, 0.)
        p.extra = image
        return p


def group_points(coords):
    # print "============================================"
    # print "FILTERING COORDS TO CREATE CLOUDS"
    # print "============================================"
    clouds = []
    vincenty = VincentyDistance()
    for point in coords:
        newcloud = {}
        newcloud['points'] = [point]
        newcloud['center'] = point
        if not len(clouds):
            clouds.append(newcloud)
            continue
        for cloud in clouds:
            p = cloud['center']
            if not point.equals(p):
                d = vincenty.distance(point, p)
            else:
                d = 0.
            if d < RADIUS:
                cloud['points'].append(point)
                cloud['center'] = calculate_cloud_center(cloud['points'])
                newcloud = None
                break
        if newcloud:
            clouds.append(newcloud)
    # print "Number of clouds: {}".format(len(clouds))
    coords = []
    coords = map(lambda x: x['center'], clouds)
    return coords


def filter_coords(coords, limits, center, width, height):
    parts = center.split('_')
    # Getting bounds for grid rectangle given by center
    step_x = (limits['max_lng'] - limits['min_lng']) / width
    step_y = (limits['max_lat'] - limits['min_lat']) / height
    filtered_coords = []
    for point in coords:
        if point.lat > limits['min_lat'] and point.lat < limits['max_lat']\
            and point.lng > limits['min_lng'] and point.lng < limits['max_lng']:
            filtered_coords.append(point)
    return filtered_coords


def calculate_cloud_center(cloud):
    size = len(cloud)
    center = Point(0., 0., 0.)
    center = reduce(lambda p1, p2: Point(p1.lat + p2.lat, p1.lng + p2.lng, p1.alt + p2.alt), cloud)
    center /= size
    center.extra = 'CENTER'
    return center


def process_images():
    coords = []
    for image in IMAGES:
        exif_info = get_exif(image)
        p = get_point_from_exif(image, exif_info)
        if not p:
            continue
        coords.append(p)
    urls = generate_map_urls(coords, WIDTH, HEIGHT)
    call_paths(urls, prefix='map')
    generate_composite_map(urls, WIDTH, HEIGHT)


def generate_composite_map(urls, width, height):
    centers = []
    for url in urls:
        param = url[url.rfind('&center=')+8:]
        center = (float(param.split(',')[1]), float(param.split(',')[0]))
        centers.append(center)
    vincenty = VincentyDistance()
    horiz_dist = 0
    vert_dist = 0
    if width > 1:
        p1 = Point(centers[0][1], centers[0][0])
        p2 = Point(centers[1][1], centers[1][0])
        horiz_dist = vincenty.distance(p1, p2)
    if height > 1:
        p1 = Point(centers[0][1], centers[0][0])
        p2 = Point(centers[width][1], centers[width][0])
        vert_dist = vincenty.distance(p1, p2)
    dist_zoom = max_width / math.pow(2, ZOOM)
    print "Distance represented in this zoom level: ", dist_zoom
    offset_x = int(horiz_dist / dist_zoom * 1280)
    print "Distance between horizontal centers: ", offset_x
    offset_y = int(vert_dist / dist_zoom * 1280)
    print "Distance between vertical centers: ", offset_y
    print "Generating image of {}, {}".format(1280 + (width - 1) * offset_x, 1280 + (height - 1) * offset_y)
    composite = Image.new("RGB", (1280 + (width - 1) * offset_x, 1280 + (height - 1) * offset_y))
    for i in range(height):
        for j in reversed(range(width)):
            image = Image.open('map_{:04d}.png'.format(j + (height - i - 1) * width))
            composite.paste(image, (j * offset_x + j, i * offset_y + 6 + i))
            composite.save('composite.png')
            


def process_paths():
    url = generate_paths_url(SOURCES, DESTINATIONS)
    call_paths(url, prefix='path')


def process_path():
    urls = generate_paths_urls(PATH, WIDTH, HEIGHT)
    call_paths(urls, prefix='path')


def call_paths(urls, prefix='map'):
    i = 0
    percent = 0

    for url in urls:
        sys.stdout.write("\rGenerating images... {}%".format(percent))
        sys.stdout.flush()
        req = Request(url)
        response = urllib2.urlopen(req)
        m = response.read()
        parser = ImageFile.Parser()
        parser.feed(m)
        image = parser.close()
        filename = '{}_{:04d}.png'.format(prefix, i)
        i = i + 1
        percent = percent + 100 / len(urls)
        image.save(filename)
    sys.stdout.write("\rGenerating images... 100%. Complete!\n".format(percent))
    sys.stdout.flush()


def generate_paths_url(sources, destinations):
    base_url = 'http://maps.googleapis.com/maps/api/staticmap?size=640x640&'
    params = {}
    params['format'] = 'png'
    params['sensor'] = 'false'
    params['visual_refresh'] = 'false'
    params['maptype'] = 'hybrid'
    params['zoom'] = ZOOM
    params['scale'] = 2
    base_url += urllib.urlencode(params)
    for source in sources:
        for destination in destinations:
            base_url += '&path=color:0xff0000ff|weight:1|geodesic:true'
            base_url += urllib.urlencode('|' + source)
            base_url += urllib.urlencode('|' + destination)
    return base_url


def generate_map_urls(coords, width=1, height=1):
    locs = []
    for p in coords:
        loc = {'lat':p.lat, 'lng':p.lng}
        locs.append(loc)
    urls = []
    global ZOOM, FRAME
    # Get the max and min coordinates for the set of locations
    limits = get_bounds(locs, FRAME)
    params = {}
    params['format'] = 'png'
    params['sensor'] = 'false'
    params['visual_refresh'] = 'false'
    params['maptype'] = 'hybrid'
    if ZOOM is None:
        ZOOM = calc_zoom(limits, width, height)
    params['zoom'] = ZOOM
    params['scale'] = 2
    icon = 'http://static.wixstatic.com/media/e58584_1c9656aa0f014fe3980eed3c73797514.png_srz_p_57_40_75_22_0.50_1.20_0.00_png_srz'
    # Calculate the center of each section of the map, depending on
    # the number of tiles in width and height
    centers = get_centers(limits, width, height)
    # Generate the urls
    for center in sorted(centers):
        filtered_coords = []
        grouped_points = []
        base_url = 'http://maps.googleapis.com/maps/api/staticmap?size=640x640&'
        base_url += urllib.urlencode(params)
        base_url += '&markers=icon:' + icon
        filtered_coords = filter_coords(coords, limits, center, width, height)
        if filtered_coords is None:
            continue
        grouped_points = group_points(filtered_coords)
        for point in grouped_points:
            base_url += '%7C{:2.6f},{:3.6f}'.format(point.lat,point.lng)
        base_url += '&center=' + str(centers[center][1]) + ',' + str(centers[center][0])
        #base_url += '&markers=color:red%7C{:2.6f},{:3.6f}'.format(centers[center][1],centers[center][0])
        #base_url += '&markers=color:yellow%7C{:2.6f},{:3.6f}'.format(limits['min_lat'], limits['min_lng'])
        #base_url += '&markers=color:yellow%7C{:2.6f},{:3.6f}'.format(limits['min_lat'], limits['max_lng'])
        #base_url += '&markers=color:yellow%7C{:2.6f},{:3.6f}'.format(limits['max_lat'], limits['min_lng'])
        #base_url += '&markers=color:yellow%7C{:2.6f},{:3.6f}'.format(limits['max_lat'], limits['max_lng'])
        urls.append(base_url)
    return urls


def calc_zoom(limits, width, height):
    diff_latitude = limits['max_lat'] - limits['min_lat']
    diff_longitude = limits['max_lng'] - limits['min_lng']
    step_x = float((limits['max_lng'] - limits['min_lng']) / width)
    step_y = float((limits['max_lat'] - limits['min_lat']) / height)
    # Whole Earth in Equator is shown in 256x256 map, so in 640x640,
    # Earth is shown 2.5 times
    # Width is the Equator circumference times 2.5
    dist_x = mean_radius * diff_longitude * 2 * math.pi / 360
    dist_y = mean_radius * diff_latitude * 2 * math.pi / 360
    max_step = max(dist_x / width, dist_y / height)
    # A zoom level represents a distance half the distance of the
    # immediately upper level and double the distance of the immediately
    # lower level, so we must use base-2 logarithm to calculate the
    # appropriate level to show a certain distance
    quotient = max_width / max_step
    zoom = int(math.log(quotient, 2))
    return zoom


def generate_paths_urls(legs, width=1, height=1):
    # Get the coordinates for every leg in the path
    locs = [get_geolocation(leg) for leg in legs]
    global ZOOM, CAR, FRAME
    # Get the max and min coordinates for the set of locations
    limits = get_bounds(locs, FRAME)
    urls = []
    params = {}
    params['format'] = 'png'
    params['sensor'] = 'false'
    params['visual_refresh'] = 'false'
    params['maptype'] = 'hybrid'
    if ZOOM is None:
        ZOOM = calc_zoom(limits, width, height)
    params['zoom'] = ZOOM
    params['scale'] = 2
    # Calculate the center of each section of the map, depending on
    # the number of tiles in width and height
    centers = get_centers(limits, width, height)
    if CAR == True:
        directions = get_directions(legs[0], legs[len(legs)-1], legs[1:len(legs)-1])
        polyline = directions['routes'][0]['overview_polyline']['points']
        dist = 0.0
        for l in directions['routes'][0]['legs']:
            distance = l['distance']['value']
            print "Distance from {} to {}: {:.3f}km".format(l['start_address'], l['end_address'], distance / 1000.0)
            dist += distance
        print "Total distance: {:.3f}km ({:.3f}nm)".format(dist / 1000.0, dist / 1852.0)
    else:
        vincenty = VincentyDistance()
        dist = 0
        for i in range(len(locs) - 1):
            p1 = Point(locs[i]['lat'], locs[i]['lng'])
            p2 = Point(locs[i+1]['lat'], locs[i+1]['lng'])
            distance = vincenty.distance(p1, p2)
            print "Distance from {} to {}: {:.3f}".format(legs[i], legs[i+1], distance / 1000.0)
            dist = dist + distance
        print "Total distance (one-way): {:.3f}km ({:.3f}nm)".format(dist / 1000.0, dist / 1852.0)

    # Generate the urls
    icon = 'http://static.wixstatic.com/media/e58584_1c9656aa0f014fe3980eed3c73797514.png_srz_p_57_40_75_22_0.50_1.20_0.00_png_srz'
    for center in sorted(centers):
        base_url = 'http://maps.googleapis.com/maps/api/staticmap?size=640x640&'
        base_url += urllib.urlencode(params)
        base_url += '&markers=icon:' + icon
        for leg in legs:
            base_url += '|' + urllib.quote_plus(leg)
        base_url += '&center=' + str(centers[center][1]) + ',' + str(centers[center][0])
        # base_url += '&markers=color:red%7C{:2.6f},{:3.6f}'.format(centers[center][1],centers[center][0])
        # base_url += '&markers=color:yellow%7C{:2.6f},{:3.6f}'.format(limits['min_lat'], limits['min_lng'])
        # base_url += '&markers=color:yellow%7C{:2.6f},{:3.6f}'.format(limits['min_lat'], limits['max_lng'])
        # base_url += '&markers=color:yellow%7C{:2.6f},{:3.6f}'.format(limits['max_lat'], limits['min_lng'])
        # base_url += '&markers=color:yellow%7C{:2.6f},{:3.6f}'.format(limits['max_lat'], limits['max_lng'])
        # print base_url
        if CAR == True:
            base_url += '&path=color:0x0000ffff|weight:2|enc:' + polyline
        else:
            base_url += '&path=color:0x0000ffff|weight:2|geodesic:true'
            for leg in legs:
                base_url += '|' + urllib.quote_plus(leg)
        urls.append(base_url)
    return urls


def get_geolocation(leg):
    url = 'http://maps.googleapis.com/maps/api/geocode/json?sensor=false&address=' + urllib.quote_plus(leg)
    req = Request(url)
    response = urllib2.urlopen(req)
    m = response.read()
    s = json.loads(m)
    return s['results'][0]['geometry']['location']


def get_directions(source, destination, waypoints=None):
    url = 'http://maps.googleapis.com/maps/api/directions/json?'
    params = {}
    params['origin'] = source
    params['destination'] = destination
    params['sensor'] = 'false'
    url += urllib.urlencode(params)
    if waypoints is not None:
        url += '&waypoints='
        for waypoint in waypoints:
            url += urllib.quote_plus(waypoint) + '|'
    req = Request(url)
    response = urllib2.urlopen(req)
    m = response.read()
    s = json.loads(m)
    return s


def get_bounds(locations, frame_percent=0.05):
    bounds = {}
    max_lat,min_lat = -90,90
    max_lng,min_lng = -180,180
    for lat in (loc['lat'] for loc in locations):
        max_lat,min_lat = max(lat, max_lat), min(lat, min_lat)
    for lng in (loc['lng'] for loc in locations):
        max_lng,min_lng = max(lng, max_lng), min(lng, min_lng)
    frame = max(max_lat-min_lat, max_lng-min_lng) * float(frame_percent)
    bounds['max_lat'], bounds['min_lat'] = max_lat + frame, min_lat - frame
    bounds['max_lng'], bounds['min_lng'] = max_lng + frame, min_lng - frame
    return bounds


def get_centers(limits, width, height):
    centers = {}
    step_x = float((limits['max_lng'] - limits['min_lng']) / width)
    step_y = float((limits['max_lat'] - limits['min_lat']) / height)
    for y in range(height):
        for x in range(width):
            cx = limits['min_lng'] + (x * step_x) + (step_x / 2.0)
            cy = limits['min_lat'] + y * step_y + (step_y / 2.0)
            centers[str(y) + '_' + str(x)] = (cx, cy)
    return centers


def main():
    parser = ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-a", "--all", dest="all", action="store_true", help="process all images in directory")
    group.add_argument("-s", "--sources", nargs='+', dest="sources", action="store", help="specify sources for paths")
    group.add_argument("-p", "--path", nargs='+', dest="path", action="store", help="specify points of path")
    parser.add_argument("-d", "--destinations", nargs='+', dest="destinations", action="store", help="specify destinations for paths")
    group.add_argument("-i", "--images", nargs='+', dest="images", action="store",\
        help="comma separated list with image filenames to process")
    parser.add_argument("-r", "--radius", type=int, dest="radius", action="store",\
        help="minimum distance between two markers in the final image")
    parser.add_argument("-w", "--width", type=int, dest="width", action="store",\
        help="specify the number of horizontal tiles in the grid (default = 1)")
    parser.add_argument("-e", "--height", type=int, dest="height", action="store",\
        help="specify the number of vertical tiles in the grid (default = 1)")
    parser.add_argument("-z", "--zoom", type=int, dest="zoom", action="store",\
        help="specify the zoom to be used in the maps (default = 3)")
    parser.add_argument("-c", "--car", dest="car", action="store_true", help="select car as the vehicle for map")
    parser.add_argument("-f", "--frame", dest="frame", action="store", help="percent of the grid side to extend the margins of the map")
    options = parser.parse_args()

    global IMAGES, SOURCES, DESTINATIONS, RADIUS, PATH, WIDTH, HEIGHT, ZOOM, CAR, FRAME
    CAR = False
    WIDTH = 1
    HEIGHT = 1
    ZOOM = None
    FRAME = 0.05

    # Process msisdn option
    if options.images:
        try:
            # Check several filenames separated by commas
            IMAGES = [image for image in options.images]
        except Exception:
            print("Bad list of filenames given")
            sys.exit(-1)
    elif options.all:
        IMAGES = []
        for files in os.listdir("."):
            if files.endswith(".JPG"):
                IMAGES.append(files)
    elif options.path:
        PATH = [leg for leg in options.path]
    elif options.sources:
        SOURCES = [source for source in options.sources]
        print SOURCES, len(SOURCES)
        if options.destinations:
            DESTINATIONS = [dest for dest in options.destinations]
        else:
            print "Sources found but no destinations given"
            sys.exit(-1)
    # If radius is not provided, the default value will be 1000m
    if options.radius:
        RADIUS = options.radius
    else:
        RADIUS = 1000
    
    if options.width:
        WIDTH = options.width

    if options.height:
        HEIGHT = options.height
    
    if options.zoom:
        ZOOM = options.zoom
    
    if options.car:
        CAR = True
    
    if options.frame:
        FRAME = float(options.frame)

    if "IMAGES" in globals():
        process_images()
    elif "SOURCES" in globals():
        process_paths()
    elif "PATH" in globals():
        process_path()

if __name__ == '__main__':
    main()
