#!/usr/bin/env python
#
# Version for importing Yocto build manifest
#
# The build manifest file is located in <project path>/build/tmp/deploy/images/<machine name>/<image name>-<machine name>.manifest
# (for example <project path>/build/tmp/deploy/images/wac-gen2/wac-core-image-wac-gen2.manifest)
#
# This script operates in 2 modes as follows:
# 1. Mode kblookup: Accept input file, read list of components & versions from the file, producing an output list of BD URLs for KB components which match the component
#    name and version
# 2. Mode import: Accept input file, seed file, project name and version - Read list of components & version from the input file in addition to a seed file of BD URLs
#    (produced by mode 1), find matching KB component & version and (if not already in project) add as manual component to specified project & version
#
# Supports replacement file to skip components and replace component names (-r)
# File format:
#   component_name;replacement_string
#   skip_string;SKIP
#
# SKIP is used to skip components starting with skip_string. This is required because the build manifest includes a large number of kernel components which do not match in the KB for example:
#   kernel-module-6lowpan-4.14.68
#   kernel-module-6pack-4.14.68
#   kernel-module-8021q-4.14.68
#   kernel-module-8192cu-4.14.68
#
# The following line would be needed to ignore all matching kernel modules:
#   kernel-module;SKIP

import argparse
#import json
import logging
import re
from difflib import SequenceMatcher

from blackduck.HubRestApi import HubInstance

logging.basicConfig(filename='import_yocto_build_manifest.log',level=logging.INFO)

hub = HubInstance()

kblookupdict = {}   # Dict of component names from kbfile with matching array of component URLs for each
kbverdict = {}      # Dict of component/version strings with single component version URL for each
kbnomatchcomplist = []  # List of components which returned no match in KB
manualcomplist = {} # Dict of manually added components for optional deletion if -d specified
repdict = {}        # Dict of component name replacement strings
skiplist = []       # List of component name strings to skip
listfile = ""

def get_kb_component(componentname):
    #print("DEBUG: processing component {}".format(componentname))
    componentname = componentname.replace(" ", "+")
    #packagename = packagename.replace("-", "+")
    req_url = hub.get_urlbase() + "/api/search/components?q=name:{}&limit={}".format(componentname, 20)
    try:
        response = hub.execute_get(req_url)
    except:
        logging.error("get_kb_component(): Exception trying to find KB matches")

    if response.status_code != 200:
        logging.error("Failed to retrieve KB matches, status code: {}".format(response.status_code))

    return response

def find_ver_from_compver(kburl, version):
    matchversion = ""

    component = hub.execute_get(kburl)
    if component.status_code != 200:
        logging.error("Failed to retrieve component, status code: {}".format(component.status_code))
        return "", "", 0, "", ""
    bdcomp_sourceurl = component.json().get('url')
    #
    # Request the list of versions for this component
    compname = component.json().get('name')
    respitems = component.json().get('_meta')
    links = respitems['links']
    vers_url = links[0]['href'] + "?limit=3000"
    kbversions = hub.execute_get(vers_url)
    if kbversions.status_code != 200:
        logging.error("Failed to retrieve component, status code: {}".format(kbversions.status_code))
        return "", "", 0, "", ""

    localversion = version.replace('-','.')
    for kbversion in kbversions.json().get('items'):

        kbversionname = kbversion['versionName'].replace('-', '.').replace('_', '.')
        kbver_url = kbversion['_meta']['href']
        logging.debug("component = {} searchversion = {} kbver = {} kbverurl = {}".format(compname, version, kbversionname, kbver_url))
        if ((kbversionname == localversion) or ((len(kbversionname) > 2) and (kbversionname.lower()[0] == 'v') and (kbversionname[1:] == localversion))):
            # exact version string match
            matchversion = kbversion['versionName']
            matchstrength = 3
            break

#
#         # Need to look for partial matches
#         seq = SequenceMatcher(None, kbversionname, localversion)
#         match = seq.find_longest_match(0, len(kbversionname), 0, len(localversion))
#         if (match.a == 0) and (match.b == 0) and (match.size == len(kbversionname)):
#             # Found match of full kbversion at start of search_version
#             if len(kbversionname) > len(matchversion):
#                 # Update if the kbversion is longer than the previous match
#                 matchversion = kbversion['versionName']
#                 matchstrength = 2
#                 logging.debug("Found component block 1 - version="+ matchversion)
#
#         elif (match.b == 0) and (match.size == len(localversion)):
#             # Found match of full search_version within kbversion
#             # Need to check if kbversion has digits before the match (would mean a mismatch)
#             mob = re.search('\d', kbversionname[0:match.a])
#             if not mob and (len(kbversionname) > len(matchversion)):
#                 # new version string matches kbversion but with characters before and is longer than the previous match
#                 matchversion = kbversion['versionName']
#                 logging.debug("Found component block 2 - version="+ matchversion)
#                 if (match.a == 1) and (kbversionname.lower() == 'v' ):  # Special case of kbversion starting with 'v'
#                     matchstrength = 3
#                 else:
#                     matchstrength = 2

#         elif (match.a == 0) and (match.b == 0) and (match.size > 2):
#             # both strings match at start for more than 2 characters min
#             # Need to try close numeric version match
#             # - Get the final segment of searchversion & kbversion
#             # - Match if 2 versions off?
#             if 0 <= match.size - localversion.rfind(".") <= 2:
#                 # common matched string length is after final .
#                 kbfinalsegment = kbversionname.split(".")[-1]
#                 localfinalsegment = localversion.split(".")[-1]
#                 if (kbfinalsegment.isdigit() and localfinalsegment.isdigit()):
#                     # both final segments are numeric
#                     logging.debug("kbfinalsegment = " + kbfinalsegment + " localfinalsegment = " + localfinalsegment + " matchversion = " + matchversion)
#                     if abs(int(kbfinalsegment) - int(localfinalsegment)) <= 2:
#                         # values of final segments are within 2 of each other
#                         if len(kbversionname) >= len(matchversion):
#                             # kbversion is longer or equal to matched version string
#                             matchversion = kbversion['versionName']
#                             matchstrength = 1
#                             logging.debug("Found component block 3 - version="+ matchversion)

    if matchversion != "":
        srcurl = bdcomp_sourceurl
        if bdcomp_sourceurl:
            if bdcomp_sourceurl.count(";") > 0:
                srcurl = bdcomp_sourceurl.replace(';','')
        return compname, matchversion, matchstrength, srcurl, kbver_url

    return "", "", 0, "", ""

def find_ver_from_hits(hits, search_version):
    matchversion = ""
    matchstrength=0
    for hit in hits:
        #
        # Get component from URL
        comp_url = hit['component']
        foundcompname, matchversion, matchstrength, bdcomp_sourceurl, bdcompver_url = find_ver_from_compver(comp_url, search_version)
        if matchstrength == 3:
            break

    if matchversion == "":
        if search_version.count("+") > 0:
            search_version = search_version.split("+")[0]
            for hit in hits:
                #
                # Get component from URL
                comp_url = hit['component']
                foundcompname, matchversion, matchstrength, bdcomp_sourceurl, bdcompver_url = find_ver_from_compver(comp_url, search_version)
                if matchstrength == 3:
                    break
    if matchversion == "":
        return "", "", 0, "", "", ""
    else:
        return foundcompname, matchversion, matchstrength, bdcomp_sourceurl, comp_url, bdcompver_url


def search_kbcomponent(component, version):
    if component in kbnomatchcomplist:
        return "", "", 0, "", "", ""

    compver = component + "/" + version
    if compver in kbverdict:
        # Already matched this
        return component, version, 3, "", kbverdict[compver].rsplit("/", 2)[0], kbverdict[compver]

    response = get_kb_component(component)
    if response.status_code != 200:
        return "", "", 0, "", "", ""

    respitems = response.json().get('items', [])
    #logging.debug("{} items returned".format(respitems[0]['searchResultStatistics']['numResultsInThisPage']))
    if respitems[0]['searchResultStatistics']['numResultsInThisPage'] > 0:
        temp_comp, temp_version, matchstrength, temp_srcurl, temp_compurl, temp_compverurl = find_ver_from_hits(respitems[0]['hits'], version)
        return temp_comp, temp_version, matchstrength, temp_srcurl, temp_compurl, temp_compverurl
    else:
        kbnomatchcomplist.append(component)
        return "", "", 0, "", "", ""

def find_comp_from_kb(compname, version, outkbfile, inkbfile, repdict):
    #
    # Try to find component in KB
    #
    end = False
    found_comp = ""
    found_version = ""
    comp_url = ""
    compver_url = ""
    source_url = ""
    max_matchstrength = 0

    origcomp = compname
    #
    # Replace component names from replacement file
    if compname in repdict:
        compname = repdict[compname]

    while end == False:
        logging.info("Searching KB for component '{}'".format(compname))
        temp_comp, temp_version, matchstrength, temp_srcurl, temp_compurl, temp_compverurl = search_kbcomponent(compname, version)
        if matchstrength > 0:
            logging.info("Matched version {} with strength {}".format(temp_version, matchstrength))
        if matchstrength == 3:
            end = True
        if matchstrength > max_matchstrength:
            max_matchstrength = matchstrength
            found_comp = temp_comp
            found_version = temp_version
            comp_url = temp_compurl
            compver_url = temp_compverurl
            source_url = temp_srcurl

        if (end == False) and (len(compname) == len(origcomp)) and (compname.find("-") > -1):
            compnamecolons = compname.replace("-", "::")
            compnamecolons = compnamecolons.replace("_", "::")
            logging.info("Searching KB for component '{}'".format(compnamecolons))
            temp_comp, temp_version, matchstrength, temp_srcurl, temp_compurl, temp_compverurl = search_kbcomponent(compnamecolons, version)
            if matchstrength > 0:
                logging.info("Matched version {} with strength {}".format(temp_version, matchstrength))
            if matchstrength == 3:
                end = True
            if matchstrength > max_matchstrength:
                max_matchstrength = matchstrength
                found_comp = temp_comp
                found_version = temp_version
                comp_url = temp_compurl
                compver_url = temp_compverurl
                source_url = temp_srcurl

        if (end == False) and ((compname.find("-") > -1) or (compname.find("_") > -1)):
            #
            # Process component replacing - with spaces
            compnamespaces = compname.replace("-", " ")
            compnamespaces = compnamespaces.replace("_", " ")
            logging.info("Searching KB for component '{}'".format(compnamespaces))
            temp_comp, temp_version, matchstrength, temp_srcurl, temp_compurl, temp_compverurl = search_kbcomponent(compnamespaces, version)
            if matchstrength > 0:
                logging.info("Matched version {} with strength {}".format(temp_version, matchstrength))
            if matchstrength == 3:
                end = True
            if matchstrength > max_matchstrength:
                max_matchstrength = matchstrength
                found_comp = temp_comp
                found_version = temp_version
                comp_url = temp_compurl
                compver_url = temp_compverurl
                source_url = temp_srcurl

        if end == False:
            #
            # Remove trailing -xxx from package name
            newcompname = compname.rsplit("-", 1)[0]
            if len(newcompname) == len(compname):
                #
                # No - found, try removing trailing .xxxx
                newcompname = compname.rsplit(".", 1)[0]
                if (len(newcompname) == len(compname)):
                    end = True
            compname = newcompname

    if max_matchstrength > 0:
        logging.info("Component matched and added to output KBLookup file")
        listoutput(" - MATCHED '{}/{}'".format(found_comp, found_version), True)
        kblookupdict.setdefault(compname, []).append(comp_url)
        kbverdict[compname + "/" + version] = compver_url
        if source_url:
            if source_url.count(";") > 0:
                source_url = source_url.replace(";", "")
        return "{};{};{};{};{};{};\n".format(origcomp,found_comp,source_url,comp_url,version,compver_url)

    else:
        logging.info("Component NOT matched - NO MATCH added to output KBLookup file")
        listoutput(" - NO MATCH", True)
        return "{};;;NO MATCH;{};NO VERSION MATCH;\n".format(origcomp, version)

def add_kbfile_entry(outkbfile, line):
    try:
        ofile = open(outkbfile, "a+")
    except:
        logging.error("append_kbfile(): Failed to open file {} for read".format(outkbfile))
        return

    ofile.write(line)
    ofile.close()

def update_kbfile_entry(outkbfile, package, version, compurl, kbverurl):
    #
    # Append version strings to kbfile entry
    #
    # FIELDS:
    # 1 = Local component name;
    # 2 = KB component name;
    # 3 = KB component source URL;
    # 4 = KB component URL;
    #
    # OPTIONAL:
    # 5 = Local component version string
    # 6 = KB Component version URL
    # (Repeated as often as matched)
    try:
        ofile = open(outkbfile, "r")
    except:
        logging.error("update_kbfile(): Failed to open file {} for read".format(outkbfile))
        return

    lines = ofile.readlines()
    ofile.close()

    try:
        ofile = open(outkbfile, "w")
    except:
        logging.error("update_kbfile(): Failed to open file {} for write".format(outkbfile))
        return

    for line in lines:
        elements = line.split(";")
        compname = elements[0]
        thiscompurl = elements[3]
        if compname != package:
            ofile.write(line)
        else:
            if compurl != thiscompurl:
                ofile.write(line)
            else:
                ofile.write("{}{};{};\n".format(line.rstrip(), version, kbverurl))
                logging.debug("update_kbfile(): updated kbfile line with '{};{};'".format(version, kbverurl))

    ofile.close()
    return

def import_kbfile(kbfile, outfile):
    #
    # If outfile is not "" then copy kbfile to outfile
    #
    # FIELDS:
    # 1 = Local component name;
    # 2 = KB component name;
    # 3 = KB component source URL;
    # 4 = KB component URL;
    #
    # OPTIONAL:
    # 5 = Local component version string
    # 6 = KB Component version URL
    # (Repeated as often as matched)

#    kblookupdict = {}
#    kbverdict = {}
    output = False
    try:
        kfile = open(kbfile, "r")
    except:
        logging.error("import_kbfile(): Failed to open file {} ".format(kbfile))
#        return kblookupdict, kbverdict
        return

    print("Reading Input KB Lookup file {} ...".format(kbfile))
    if outfile != "" and outfile != kbfile:
        output = True
        try:
            ofile = open(outfile, "a+")
        except:
            logging.error("import_kbfile(): Failed to open file {} ".format(outfile))
#            return "",""
            return

    lines = kfile.readlines()

    count = 0
    for line in lines:
        elements = line.split(";")
        compname = elements[0]
        kbcompurl = elements[3]
        #if kbcompurl != "NO MATCH":
        #kblookupdict[compname] = kbcompurl
        kblookupdict.setdefault(compname, []).append(kbcompurl)
        index = 4
        while index < len(elements) - 1:
            kbverdict[compname + "/" + elements[index]] = elements[index+1]
            index += 2
        #elif kbcompurl == "NO MATCH":
        #    kblookupdict.setdefault(compname, []).append("NO MATCH")
        count += 1
        if output:
            ofile.write(line)

    kfile.close
    if output:
        ofile.close()

    print("Processed {} entries from {}".format(count, kbfile))
#    return kblookupdict, kbverdict
    return

def find_compver_from_compurl(package, kburl, search_version):
    compname, matchversion, matchstrength, bdcomp_sourceurl, bd_verurl = find_ver_from_compver(kburl, search_version)
    if matchstrength > 0:
        logging.info("Found version match {}".format(matchversion))
        return bd_verurl, bdcomp_sourceurl
    else:
        logging.info("No version match found")
        return "NO VERSION MATCH", ""

def add_comp_to_bom(bdverurl, kbverurl, compfile, compver):

    posturl = bdverurl + "/components"
    custom_headers = {
            'Content-Type':'application/vnd.blackducksoftware.bill-of-materials-6+json'
    }

    postdata =  {
            "component" : kbverurl,
            "componentPurpose" : "import_manifest: imported from file " + compfile,
            "componentModified" : False,
            "componentModification" : "Original component = " + compver
    }

    #print("POST command - posturl = {} postdata = {}".format(posturl, postdata, custom_headers))
    response = hub.execute_post(posturl, postdata, custom_headers)
    if response.status_code == 200:
        print(" - Component added")
        logging.debug("Component added {}".format(kbverurl))
        return True
    else:
        print(" - Component NOT added (Already exists)")
        logging.error("Component NOT added {}".format(kbverurl))
        return False

def del_comp_from_bom(compurl):

    response = hub.execute_delete(compurl)
    if response.status_code == 200:
        logging.debug("Component deleted {}".format(compurl))
        return True
    else:
        logging.error("Component NOT deleted {}".format(compurl))
        return False

def manage_project_version(proj, ver):
    bdproject = hub.get_project_by_name(proj)
    if not bdproject:
        resp = hub.create_project(proj, ver)
        if resp.status_code != 201:
            logging.debug("Cannot create project {}".format(proj))
            return None, None

        print("Created project '{}'".format(proj))
        bdproject = hub.get_project_by_name(proj)
    else:
        print("Opening project '{}'".format(proj))

    bdversion = hub.get_version_by_name(bdproject, ver)
    if not bdversion:
        resp = hub.create_project_version(bdproject, ver)
        if resp.status_code != 201:
            logging.debug("Cannot create version {}".format(ver))
            return None, None
        print("Created version '{}'".format(ver))
        bdversion = hub.get_version_by_name(bdproject, ver)
    else:
        print("Opening version '{}'".format(ver))
    return bdproject, bdversion


def read_compfile(compfile):
    try:
        cfile = open(compfile)
    except:
        logging.error("Failed to open file {} ".format(compfile))
        return None

    if cfile.mode != 'r':
        logging.error("Failed to open file {} ".format(compfile))
        return None

    lines = cfile.readlines()

    return lines


def process_compfile_line(line, skiplist):
# Example line from build manifest:
#     alsa-utils-alsamixer aarch64 1.1.5
#
    splitline = line.rstrip().split(" ")
    if len(splitline) != 3:
        logging.error("Invalid build manifest line format - expecting '<comp> <arch> <version'")
        return("", "", True)

    vername = splitline[2]
    plus = vername.count("+")
    if (plus > 0):
        pos = vername.index("+")
        if (len(vername) > pos + 1) and vername[pos+1:].isdigit():
            vername = vername[0:pos]
    for skipstring in skiplist:
        if splitline[0].find(skipstring) == 0:
            return(splitline[0], vername, True)

    return(splitline[0], vername, False)
    #
    # 3rd return parameter is whether this line should be SKIPPED


def process_replacement_file(repfile):
    repdict = {}
    skiplist = []
    try:
        rfile = open(repfile)
    except:
        logging.error("Failed to open file {} ".format(repfile))
        return None

    if rfile.mode != 'r':
        logging.error("Failed to open file {} ".format(repfile))
        return None

    rlines = rfile.readlines()

    for line in rlines:
        if line.count(";") == 0:
            continue
        splitline = line.rstrip().split(";")
        if splitline[1] == "SKIP":
            skiplist.append(splitline[0])
            print("Will Skip components starting with {}".format(splitline[0]))
            logging.info("Will Skip components starting with {}".format(splitline[0]))
        else:
            repdict[splitline[0]] = splitline[1]
            logging.info("Adding replacement {} for component {}".format(splitline[1], splitline[0]))

    return repdict, skiplist

def listoutput(outline, newline):
    if listfile:
        try:
            ofile = open(listfile, "a+")
        except:
            logging.error("Failed to open output listfile {} for append".format(listfile))
            return
        if newline:
            ofile.write(outline + "\n")
        else:
            ofile.write(outline)
        ofile.close()

    if newline:
        print(outline)
    else:
        print(outline, end = "", flush = True)

#
# Main Program

parser = argparse.ArgumentParser(description='Process or import yocto build manifest list into project/version', prog='import_yocto_build_manifest')

subparsers = parser.add_subparsers(help='Choose operation mode', dest='command')
# create the parser for the "kblookup" command
parser_g = subparsers.add_parser('kblookup', help='Process build manifest to find matching KB URLs & export to file')
parser_g.add_argument('-c', '--component_file', help='Input build manifest file', required=True)
parser_g.add_argument('-r', '--replace_file', help='File of input component name replacement strings and SKIP component strings', required=True)
parser_g.add_argument('-k', '--kbfile', help='Input file of KB component IDs matching manifest components')
parser_g.add_argument('-o', '--output', help='Output file of KB component IDs matching manifest components (default "kblookup.out")', default='kblookup.out')
parser_g.add_argument('-a', '--append', help='Append new KB URLs to the KB Lookup file specified in -k', action='store_true')
parser_g.add_argument('-l', '--listfile', help='Create an output file of component matches')

# create the parser for the "import" command
parser_i = subparsers.add_parser('import', help='Import build manifest into specified Black Duck project/version using KB URLs from supplied file')
parser_i.add_argument('-c', '--component_file', help='Input build manifest file', required=True)
parser_i.add_argument('-k', '--kbfile', help='Input file of KB component IDs and URLs matching manifest components', required=True)
parser_i.add_argument('-p', '--project', help='Black Duck project name',required=True)
parser_i.add_argument('-v', '--version', help='Black Duck version name',required=True)
parser_i.add_argument('-d', '--delete', help='Delete existing manual components from the project - if not specified then components will be added to the existing list', action='store_true')


#parser.add_argument("version")
args = parser.parse_args()

if not args.command:
    parser.print_help()
    exit

if args.command == 'kblookup':
    logging.info("KBLOOKUP mode")
    if args.listfile:
        listfile = args.listfile

    count_skipped = 0
    count_nokbmatch = 0
    count_alreadymatched = 0
    count_nokblookupmatch = 0
    count_newvermatch = 0
    count_novermatch = 0
    count_newmatch = 0

    if args.replace_file:
        print("Reading replacement file {} ...".format(args.replace_file))
        logging.info("Replacement file {} specified".format(args.replace_file))
        repdict, skiplist = process_replacement_file(args.replace_file)

    logging.info("Output KBlookup file {}".format(args.output))

    if args.kbfile:
        logging.info("Input KB lookup file {} specified".format(args.kbfile))
        if args.append:
            logging.info("Append flag specified - will copy input KB file to {}".format(args.output))
#            kblookupdict, kbverdict = import_kbfile(args.kbfile, args.output)
            import_kbfile(args.kbfile, args.output)
        else:
#            kblookupdict, kbverdict = import_kbfile(args.kbfile, "")
            import_kbfile(args.kbfile, "")
    #
    # Process components to find matching KB URLs - output to componentlookup.csv
    logging.info("Input component file specified {}".format(args.component_file))
    lines = read_compfile(args.component_file)

    print("")
    print("Will write to output kbfile {}".format(args.output))
    print("Processing component list file {} ...".format(args.component_file))
    processed_comps = 0
    all_comps = 0
    for line in lines:
        package, version, skip = process_compfile_line(line, skiplist)
        if package == "":
            print("ERROR: Invalid input build manifest file format")
            exit(0)

        all_comps += 1
        listoutput("Manifest Component = '{}/{}'".format(package, version), False)
        logging.info("PROCESSING COMPONENT from component file {}/{}".format(package, version))
        if skip:
            listoutput("- SKIPPED", True)
            logging.info("Component SKIPPED")
            count_skipped += 1
            continue

        if package in kblookupdict:
            #
            # Found primary package name in kbfile
            if kblookupdict[package][0] == "NO MATCH":
                count_nokblookupmatch += 1
                listoutput("- NO MATCH in input KB File", True)
                logging.info("Component found in KBlookup file, but NO MATCH entry found (No match in KB)")
                continue
            logging.info("Component found in KBLookup file")
            #
            # Check if package/version is defined in KB Lookup file
            packverstr = package + "/" + version
            if packverstr in kbverdict:
                # Found in KB ver URL list - Nothing to do
                logging.info("Component {}/{} already processed - not added".format(package, version))
                kbverurl = kbverdict[packverstr]
                listoutput(" - already MATCHED in input KB file", True)
                count_alreadymatched += 1
            else:
                #
                # Loop through component URLs to check for component version
                logging.info("Version not found in KBLookup file - searching in KB")
                foundkbversion = False
                for kburl in kblookupdict[package]:
                    logging.info("Working with first component entry from KBLookup file")
                    kbverurl, srcurl = find_compver_from_compurl(package, kburl, version, repdict)
                    if kbverurl != "NO VERSION MATCH":
                        listoutput(" - MATCHED '{}/{}'".format(package, version), True)
                        #print(" - MATCHED '{}/{}' (sourceURL={})".format(package, version, srcurl))
                        #
                        # KB version URL found
                        kbverdict[package + "/" + version] = kbverurl
                        logging.info("Matched {}/{} - Updating KBLookup file".format(package, version))
                        update_kbfile_entry(args.output, package, version, kblookupdict[package][0], kbverurl)
                        count_newvermatch += 1

                        foundkbversion = True
                        break
                if foundkbversion == False:
                    #
                    # No version match from existing KBLookup entries
                    # Need to do a final open search
                    newkbline = find_comp_from_kb(package, version, args.output, args.kbfile, repdict)
                    if newkbline.split(";")[3] != "NO MATCH":
                        add_kbfile_entry(args.output, newkbline)
                        count_newmatch += 1
                    else:
                        #
                        # No version match - need to add NO VERSION MATCH string to kbfile
                        logging.info("No version match found in KB - updating entry in output KBlookup file")
                        update_kbfile_entry(args.output, package, version, kblookupdict[package][0], "NO VERSION MATCH")
                        count_novermatch += 1
                    processed_comps += 1

        else:
            logging.info("Component not found in KBLookup file")
            newkbline = find_comp_from_kb(package, version, args.output, args.kbfile, repdict)
            if newkbline.split(";")[3] != "NO MATCH":
                count_newmatch += 1
            else:
                count_nokbmatch += 1
            add_kbfile_entry(args.output, newkbline)
            processed_comps += 1


        if processed_comps > 500:
            print("500 components processed - terminating. Please rerun with -k option to append to kbfile")
            logging.info("500 components processed - terminating early")
            break

    print("SUMMARY:")
    print(" {} Entries processed from component file".format(all_comps))
    print(" {} Components Skipped".format(count_skipped))
    print(" {} Components Not in KB".format(count_nokbmatch))
    print(" {} Components Already Matched in KBLookup file (duplicate)".format(count_alreadymatched))
    print(" {} Components Not Matched from KBLookup file".format(count_nokblookupmatch))
    print(" {} Components with New Version Match".format(count_newvermatch))
    print(" {} Components with No Version Match".format(count_novermatch))
    print(" {} Components with New Match".format(count_newmatch))
    logging.info("SUMMARY:")
    logging.info(" {} Entries processed from component file".format(all_comps))
    logging.info(" {} Components Skipped".format(count_skipped))
    logging.info(" {} Components Not in KB".format(count_nokbmatch))
    logging.info(" {} Components Already Matched in KBLookup file (duplicate)".format(count_alreadymatched))
    logging.info(" {} Components Not Matched from KBLookup file".format(count_nokblookupmatch))
    logging.info(" {} Components with New Version Match".format(count_newvermatch))
    logging.info(" {} Components with No Version Match".format(count_novermatch))
    logging.info(" {} Components with New Match".format(count_newmatch))

    exit()

if args.command == 'import':
    logging.info("KBLOOKUP mode")
    count_added = 0
    count_skipped = 0
    count_notinkb = 0
    count_alreadyexists = 0
    if args.kbfile:
        import_kbfile(args.kbfile, "")

    bdproject, bdversion = manage_project_version(args.project, args.version)
    if not bdversion:
        print("Cannot create version {}".format(args.version))
        exit()
    bdversion_url = bdversion['_meta']['href']

    print("Using component list file '{}'".format(args.component_file))
    lines = read_compfile(args.component_file)

    components = hub.get_version_components(bdversion)
    print("Found {} existing components in project".format(components['totalCount']))
    if args.delete:
        count = 0
        logging.debug("Looking through the components for project {}, version {}.".format(args.project, args.version))
        for component in components['items']:
            if component['matchTypes'][0] == 'MANUAL_BOM_COMPONENT':
                manualcomplist[component['componentName'] + "/" + component['componentVersionName']] = component['_meta']['href']
                count += 1
        print("Found {} manual components".format(count))

    print("")
    print("Processing component list ...")
    for line in lines:
        package, version, skip = process_compfile_line(line, skiplist)

        print("Manifest component to add = '{}/{}'".format(package, version), end="")

        logging.debug("Manifest component to add = '{}/{}'".format(package, version))
        kbverlurl = ""
        if package in kblookupdict:
            #
            # Check if package/version is in kbverdict
            packstr = package + "/" + version
            if packstr in kbverdict:
                #
                # Component version URL found in kbfile
               logging.debug("Compver found in kbverdict packstr = {}, kbverdict[packstr] = {}".format(packstr, kbverdict[packstr]))
               kbverurl = kbverdict[packstr]
            else:
                #
                # No match of component version in kbfile version URLs
                for kburl in kblookupdict[package]:
                    #
                    # Loop through component URLs from kbfile
                    kbverurl, srcurl = find_compver_from_compurl(package, kburl, version)
                    if kbverurl != "NO VERSION MATCH":
                        break
            if kbverurl != "NO VERSION MATCH":
                #
                # Component does not exist in project
                logging.debug("Component found in project - packstr = {}".format(packstr))
                if add_comp_to_bom(bdversion_url, kbverurl, args.component_file, package + "/" + version):
                    count_added += 1
                else:
                    count_alreadyexists += 1
                if package + "/" + version in manualcomplist:
                    del manualcomplist[package + "/" + version]
            else:
                print(" - No component match from KB (NOT ADDED)")
                count_notinkb += 1

        else:
            print (" - Does not exist in KBlookup file (SKIPPED)")
            count_skipped += 1

    print("SUMMARY:")
    print(" {} Components Added".format(count_added))
    print(" {} Components Skipped".format(count_skipped))
    print(" {} Components Not in KB".format(count_notinkb))
    print(" {} Components Already Exist".format(count_alreadyexists))

    if args.delete:
        #print("Unused components not deleted - not available until version 2019.08 which supports the required API")
        count = 0
        print("")
        print("Deleting outdated components ...", end = "")
        for compver in manualcomplist.values():
            del_comp_from_bom(compver)
            print(".", end = "", flush=True)
            count += 1
        print("")
        print("Deleted {} existing manual components".format(count))