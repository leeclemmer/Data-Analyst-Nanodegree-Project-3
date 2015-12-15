#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Overview

In this script, I will audit, clean, and export to JSON a OpenStreetMap (OSM) file
containing map data centered around Lancaster, Pennsylvania, PA. 
The specific map bounding box of the data is as follows:

Minimum latitude: 39.9050
Maximum latitude: 40.1749
Minimum longitude: -76.5699
Maximum longitude: -76.0309
"""

# Initialize
import re
import xml.etree.cElementTree as ET
import operator
import codecs
import json
from pprint import pprint

osm_filename = 'lancaster.osm'

#
# Audit
#

# Sanity Check

def count_tags(filename):
    """ Returns dictionary of all tag types and how often they've been used.
    Basic sanity check that the data matches expectation of what I should
    be getting based on https://wiki.openstreetmap.org/wiki/OSM_XML"""
    elements = {}
    
    for event, elem in ET.iterparse(filename):
        if not elements.get(elem.tag):
            elements[elem.tag] = 1
        else:
            elements[elem.tag] += 1
            
    return elements

def count_keys(filename):
    """ Returns a dictionary of 'k' values for any <tag> tag along with the count as the 
    value. Intended to allow a familiarization of the types of keys. """
    keys = {}
    
    for event, elem in ET.iterparse(filename):
        if elem.tag == 'tag':
            k = elem.attrib['k']
            if not keys.get(k):
                keys[k] = 1
            else:
                keys[k] += 1
    return keys

def sort_dict(d, asc=False):
    """ Returns a sorted dictionary in the form of a list with tuples. """
    # Approach via http://stackoverflow.com/questions/613183/sort-a-python-dictionary-by-value
    sorted_d = sorted(d.items(), key=operator.itemgetter(1))
    if not asc: sorted_d.reverse()
    return sorted_d

# Problem Characters

# Regular expressions from Unit 6 of Data Wrangling with MongoDB
# Intended to test key values against MongoDB key naming conventions
lower = re.compile(r'^([a-z]|_)*$')
lower_colon = re.compile(r'^([a-z]|_)*:([a-z]|_)*$')
problemchars = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')

def key_type(element, keys):
    """ Returns a dictionary for each type of key ('lower', 'other', etc.) with the 
    value consisting of a list containing the count and all k/v pairs matching they type. """
    if element.tag == "tag":
        k = element.attrib['k']
        if lower.search(k):
            keys['lower'][0] += 1
            keys['lower'][1].append(element.attrib)
        elif lower_colon.search(k):
            keys['lower_colon'][0] += 1
            keys['lower_colon'][1].append(element.attrib)
        elif problemchars.search(k):
            keys['problemchars'][0] += 1
            keys['problemchars'][1].append(element.attrib)
        else:
            keys['other'][0] += 1
            keys['other'][1].append(element.attrib)
        
    return keys

def audit_key_types(filename):
    """ Iterate on the <tag> elements of data file and parse tag elements. """
    keys = {"lower": [0,[]], "lower_colon": [0,[]], "problemchars": [0,[]], "other": [0,[]]}
    for _, element in ET.iterparse(filename):
        keys = key_type(element, keys)

    return keys


# Street Types

street_type_re = re.compile(r'\b\S+\.?$', re.IGNORECASE)

expected_street_type = ["Street", "Avenue", "Boulevard", "Drive", "Court", "Place", "Square", "Lane", "Road", 
            "Trail", "Parkway", "Commons", "Broadway", "Circle", "Alley", "Crossing", "Highway", "Pike", "Way"]

def audit_street_type(street_types, street_name):
    """ Updates street_types with unexpected types of streets and examples. """
    m = street_type_re.search(street_name)
    if m:
        street_type = m.group()
        if street_type not in expected_street_type:
            if not street_types.get(street_type):
                street_types[street_type] = set([street_name])
            else:
                street_types[street_type].add(street_name)

def is_street_name(elem):
    """ Returns T/F if element is street tag. """
    return (elem.attrib['k'] == "addr:street")

def audit_street_name(filename):
    """ Iterates data and audits street name. """
    street_types = {}
    for event, elem in ET.iterparse(filename, events=("start",)):
        if elem.tag == "node" or elem.tag == "way":
            for tag in elem.iter("tag"):
                if is_street_name(tag):
                    audit_street_type(street_types, tag.attrib['v'])

    return street_types


# Zip Codes

zip_code_re = re.compile(r'^[0-9][0-9][0-9][0-9][0-9]$')

# Source: http://www.zipmap.net/Pennsylvania.htm
expected_zip = ['17547','17552','17545','17543','17522','17501','17508','17601',
            '17505','17540','17529','17572','17562','17579','17560','17584',
            '17602','17565','17516','17551','17582','17603','17512','17554',
            '17604','17022','17317','17356','17368','17406','17520','17534',
            '17538','17557','17568','17576']

def audit_zip_code(zip_codes, zip_code):
    """ Updates zip_codes dict with zip code counts and 
    saves bad zip codes under "other" """
    if zip_code in expected_zip:
        zip_codes[zip_code] += 1
    else:
        zip_codes['other'].add(zip_code)

def is_zip_code(elem):
    """ Returns T/F whether element is zip code tag. """
    return (elem.attrib['k'] == "addr:postcode")

def audit_zip_codes(filename):
    """ Initializes expected zip_code dict and then iterates
    over elements to audit zip codes. """
    zip_codes = {}
    for z in expected_zip:
        zip_codes[z] = 0
    zip_codes['other'] = set()
    
    for event, elem in ET.iterparse(filename, events=("start",)):
        if elem.tag == "node" or elem.tag == "way":
            for tag in elem.iter("tag"):
                if is_zip_code(tag):
                    audit_zip_code(zip_codes, tag.attrib['v'])

    return zip_codes


#
# Clean & Export
#

def remove_problem_chars(k):
    """ Returns string k with any problemchars replaced by an underscore. """
    return problemchars.sub('_',k)

mapping = {"St":"Street",
           "St.":"Street",
           "Ave":"Avenue",
           "AVE":"Avenue",
           "AVENUE":"Avenue",
           "Aveneue":"Avenue",
           "Blvd":"Boulevard",
           "Dr":"Drive",
           "Dr.":"Drive",
           "drive":"Drive",
           "Rd.":"Road",
           "RD":"Road",
           "Rd":"Road",
           "road":"Road",
           "pike":"Pike"
            }

def update_street_name(name, mapping):
    """ Returns an updated version of a street name if the street type 
    isn't in the list of expected street types and there's a mapping for it.
    Example: "Market St" => "Market Street" """
    m = street_type_re.search(name)
    street_type = m.group()
    if street_type not in expected_street_type and \
        mapping.get(street_type):
        name = name.split(street_type,1)[0]
        name += mapping[street_type]

    return name

def update_zip_code(z):
    """ Returns clean-up zip code. """
    # Fix typo
    if z == '17250':
        return '17520'
    # Truncate extended zip codes
    elif '-' in z:
        return z.split('-')[0]
    # Fix error
    elif z.startswith('PA '):
        return z.split('PA ')[-1]
    else:
        return z

CREATED = [ "version", "changeset", "timestamp", "user", "uid"]

def clean_and_shape(element):
    node = {}
    if element.tag == "node" or element.tag == "way" :
        # Iterate through node/way attributes
        node['type'] = element.tag
        for k,v in element.attrib.iteritems():
            if k in CREATED:
                if not node.get('created'):
                    node['created'] = {}
                node['created'][k] = v
            elif k in ['lat','lon']:
                if not node.get('pos'):
                    node['pos'] = [None, None]
                if k == 'lat':
                    node['pos'][0] = float(v)
                elif k == 'lon':
                    node['pos'][1] = float(v)
            else:
                node[k] = v
        
        # Iterate through any <tag> children of node/way element
        for subelement in element.iter():
            if subelement.tag == 'tag':
                k = subelement.attrib['k']
                v = subelement.attrib['v']
                
                # Clean problem characters in key name
                k = remove_problem_chars(k)
                
                # Address
                if k.startswith('addr'):
                    addr_fields = k.split(':')
                    
                    # Clean street names 
                    if addr_fields == ['addr','street']:
                        v = update_street_name(v, mapping)
                        
                    # Clean zip codes
                    elif addr_fields == ['addr','postcode']:
                        v = update_zip_code(v)
                    if len(addr_fields) <= 2:
                        if not node.get('address'):
                            node['address'] = {}
                        node['address'][addr_fields[1]] = v
                # All other attributes
                else:
                    node[k] = v
            if subelement.tag == 'nd':
                if not node.get('node_refs'):
                    node['node_refs'] = []
                node['node_refs'].append(subelement.attrib['ref'])
        return node
    else:
        return None

def export_to_json(file_in, pretty = False):
    file_out = "{0}.json".format(file_in.split('.')[0])
    data = []
    with codecs.open(file_out, "w") as fo:
        for _, element in ET.iterparse(file_in):
            el = clean_and_shape(element)
            if el:
                data.append(el)
                if pretty:
                    fo.write(json.dumps(el, indent=2)+"\n")
                else:
                    fo.write(json.dumps(el) + "\n")
    return data


if __name__ == "__main__":

    #
    # Audit
    #

    # I will audit the following aspects of the data:
    # => The key attribute 'k' of the < tag > tag, to make sure it's compliant 
    # with MongoDB naming rules
    # => Street types: Change 'Ave' to 'Avenue', etc
    # => Zip codes: Make sure all zip codes are correct and five digits long

    # Inspect types and counts of tags
    pprint(count_tags(osm_filename))
    print '\n'

    # Check for number of key types
    key_counts = count_keys(osm_filename)
    pprint(sort_dict(key_counts))
    print '\n'

    # Check for problematic characters
    key_types = audit_key_types(osm_filename)
    for k,v in key_types.iteritems():
        print '{} count: {}'.format(k,v[0])
        pprint(v[1][:10])
        print '\n'

    # Check street types
    street_types = audit_street_name(osm_filename)
    pprint(street_types)
    print '\n'

    # Audit Zip Codes
    zip_codes = audit_zip_codes(osm_filename)
    pprint(zip_codes)
    print '\n'

    #
    # Clean & Export
    #

    # After the audit above, I've found several issues that I'll address:
    # => Not all < tag > key values ('k') are in a format acceptable as a key name in MongoDB. I'll change these to be acceptable.
    # => There are some issues around street names. I'll be updating those according to a mapping (e.g. "Ave" => "Avenue")
    # => There are some issues with the zip codes, so I'll ensure that all zip codes are strings of five digits.
    # 
    # Finally, I'll export the data into a JSON file using a the data format outlined in Unit 6 of Data Wrangling with MongoDB).
    export_to_json(osm_filename)
