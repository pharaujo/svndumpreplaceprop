#!/usr/bin/env python
#
#  Copyright (C) 2011  Pedro Araujo <phcrva at gmail dot com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

"""Pipeable script that replaces svn properties on a svn dump"""

from __future__ import with_statement

import sys
if sys.version_info[:2] < (2, 4):
    raise SystemExit("Error: You need Python 2.4 or over.")

import os, re, string, md5, csv

__author__ = 'Pedro Araujo <phcrva@gmail.com>'
__copyright__ = "Copyright 2011 Pedro Araujo"
__credits__ = ['Simon Tatham (svndumpfilter2)',
               'Martin Blais <blais@furius.ca> (svndumpfilter3)',]
__license__ = "GPL"
__version__ = "1.0.0"
__date__ = "31/08/2011"

# Constants for versions.
# Note: v3 does not really exist, see this for details:
# http://svn.haxx.se/dev/archive-2004-11/1111.shtml
__supported_versions__ = ('2', '3')

fmtequiv = {'1': 1,
            '2': 2,
            '3': 2}

format_warning = False


# Note: from Simon Tatham.
class Lump:
    """
    A class and some functions to handle a single lump of
    RFC822-ish-headers-plus-data read from an SVN dump file.
    """
    def __init__(self):
        self.hdrlist = []
        self.hdrdict = {}
        self.prop = ""
        self.text = ""
        self.proplist = []
        self.propdict = {}

    def sethdr(self, key, val):
        """
        Set header 'key' to 'val'.
        """
        if not self.hdrdict.has_key(key):
            self.hdrlist.append(key)
        self.hdrdict[key] = val

    def delhdr(self, key):
        """
        Delete the header 'key'.
        """
        if self.hdrdict.has_key(key):
            del self.hdrdict[key]
            self.hdrlist.remove(key)

    def propparse(self):
        """
        Parse the properties of the lump.
        """
        index = 0
        while 1:
            if self.prop[index:index+2] == "K ":
                wantval = 1
            elif self.prop[index:index+2] == "D ":
                wantval = 0
            elif self.prop[index:index+9] == "PROPS-END":
                break
            else:
                raise "Unrecognised record in props section"
            nlpos = string.find(self.prop, "\n", index)
            assert nlpos > 0
            namelen = string.atoi(self.prop[index+2:nlpos])
            assert self.prop[nlpos+1+namelen] == "\n"
            name = self.prop[nlpos+1:nlpos+1+namelen]
            index = nlpos+2+namelen
            if wantval:
                assert self.prop[index:index+2] == "V "
                nlpos = string.find(self.prop, "\n", index)
                assert nlpos > 0
                proplen = string.atoi(self.prop[index+2:nlpos])
                assert self.prop[nlpos+1+proplen] == "\n"
                prop = self.prop[nlpos+1:nlpos+1+proplen]
                index = nlpos+2+proplen
            else:
                prop = None
            self.proplist.append(name)
            self.propdict[name] = prop

    def setprop(self, key, val):
        """
        Set property 'key' to 'val'.
        """
        if not self.propdict.has_key(key):
            self.proplist.append(key)
        self.propdict[key] = val

    def delprop(self, key):
        """
        Delete property 'key'.
        """
        if self.propdict.has_key(key):
            del self.propdict[key]
            self.proplist.remove(key)

    def correct_headers(self):
        """
        Adjust the headers, from updated contents.
        """
        # First reconstitute the properties block.
        self.prop = ""

        if (len(self.proplist) > 0) and \
            self.hdrdict.get('Node-action') != "delete":
            for key in self.proplist:
                val = self.propdict[key]
                if val is None:
                    self.prop += "D %d\n%s\n" % (len(key), key)
                else:
                    self.prop += "K %d\n%s\n" % (len(key), key)
                    self.prop += "V %d\n%s\n" % (len(val), val)
            self.prop = self.prop + "PROPS-END\n"

        # Now fix up the content length headers.
        if len(self.prop) > 0:
            self.sethdr("Prop-content-length", str(len(self.prop)))
        else:
            self.delhdr("Prop-content-length")

        if len(self.text) > 0 or \
           (self.hdrdict.get('Node-action', None) == 'add' and
            self.hdrdict.get('Node-kind', None) == 'file' and
            not self.hdrdict.get('Node-copyfrom-path', None)):

            self.sethdr("Text-content-length", str(len(self.text)))
            m = md5.new()
            m.update(self.text)
            self.sethdr("Text-content-md5", m.hexdigest())
        else:
            self.delhdr("Text-content-length")
            self.delhdr("Text-content-md5")

        if len(self.prop) > 0 or len(self.text) > 0:
            self.sethdr("Content-length", str(len(self.prop)+len(self.text)))
        else:
            self.delhdr("Content-length")


format_re = re.compile('SVN-fs-dump-format-version: (\d+)\s*$')
uuid_re = re.compile('UUID: ([0-9a-f\-]+)\s*$')

# Note: from Martin Blais.
def read_dump_header(f):
    """
    Match and read a dumpfile's header and return the format versin and file's
    UUID.
    """
    mo_version = format_re.match(f.readline())
    assert mo_version
    f.readline()
    mo_uuid = uuid_re.match(f.readline())
    assert mo_uuid
    f.readline()

    text = '%s\n%s\n' % (mo_version.string, mo_uuid.string)
    return mo_version.group(1), mo_uuid.group(1), text


header_re = re.compile('([a-zA-Z0-9\-]+): (.*)$')

# Note: from Simon Tatham.
def read_rfc822_headers(f):
    """
    Read a set of RFC822 headers from the given file.  We return a dict and the
    set of original lines that were parsed to obtain the contents.
    """
    ret = Lump()

    lines = []
    while 1:
        s = f.readline()
        if not s:
            return None, [] # end of file

        # Watch for the newline char that ends the headers.
        if s == '\n':
            if len(ret.hdrlist) > 0:
                break # newline after headers ends them
            else:
                continue # newline before headers is simply ignored

        lines.append(s)

        mo = header_re.match(s)
        if mo is None:
            raise SystemExit("Error: Parsing header: %s" % s)

        ret.sethdr(*mo.groups())

    return ret, lines


# Note: from Simon Tatham.
def read_lump(f):
    """
    Read a single lump from the given file.

    Note: there is a single empty line that is used to conclude the RFC headers,
    and it is not part of the rest.  Then you have the properties, which are of
    exactly the property length, and right away follows the contents of exactly
    the length of the content length.  Then follows two newline characters and
    then the next lump starts.
    """
    lump, lines = read_rfc822_headers(f)
    if lump is None:
        return None
    pcl = int(lump.hdrdict.get("Prop-content-length", "0"))
    tcl = int(lump.hdrdict.get("Text-content-length", "0"))
    if pcl > 0:
        lump.prop = f.read(pcl)
        lump.propparse()
    if tcl > 0:
        lump.text = f.read(tcl)

    lump.orig_text = os.linesep.join(lines) + lump.prop + lump.text

    return lump


# Note: from Martin Blais.
def write_lump(f, lump):
    """
    Write a single lump to the given file.
    """
    # Make sure that the lengths are adjusted appropriately.
    lump.correct_headers()
    for key in lump.hdrlist:
        val = lump.hdrdict[key]
        f.write(key + ": " + val + "\n")
    f.write("\n")

    # Render the payload.
    f.write(lump.prop)
    f.write(lump.text)

    # Add newlines at the end of chunks, for readers.
    f.write('\n')
    if not lump.hdrdict.has_key("Revision-number"):
        f.write('\n')


def prop_map_parser(filename):
    prop_map = {}
    with open(filename, 'rb') as f:
        reader = csv.reader(f)
        try:
            for row in reader:
                if len(row) == 0:
                    continue
                entry = prop_map.get(row[0],list())
                entry.append((row[1], row[2],))
                prop_map[row[0]] = entry
        except csv.Error, e:
            sys.exit('file %s, line %d: %s' % (filename, reader.line_num, e))

    return prop_map


def replace_props(lump, prop_map):
    for prop, replacements in prop_map.iteritems():
        if prop in lump.propdict:
            for search, replace in replacements:
                lump.propdict[prop] = re.sub(search, replace, lump.propdict[prop])
    return lump


def parse_options():
    """
    Parse and validate the options.
    """
    import optparse
    parser = optparse.OptionParser()

    parser.add_option('-f', '--prop-map-file', dest="prop_map",
                      help="File mapping revprop transformations.")
    parser.add_option('--debug', action='store_true',
                      help=optparse.SUPPRESS_HELP)

    global opts
    opts, args = parser.parse_args()

    if not os.path.exists(opts.prop_map) or not os.path.isfile(opts.prop_map):
        parser.error("Properties map doesn't exist.")

    return opts, args


# Note: Mostly from Martin Blais.
def main():
    """
    Main program that just reads the lumps and copies them out.
    """
    opts, args = parse_options()

    # Open in and out files.
    fr = sys.stdin
    fw = sys.stdout
    flog = sys.stderr

    # Read the dumpfile header.
    format, uuid, text = read_dump_header(fr)
    fw.write(text)
    if format not in __supported_versions__:
        raise SystemExit("Error: dump file in format '%s' not supported." %
                         format)

    prop_map = prop_map_parser(opts.prop_map)
    # Process the dump file.
    while 1:
        # Read one lump at a time
        lump = read_lump(fr)
        if lump is None:
            break # At EOF

        lump = replace_props(lump, prop_map)

        # Print some kind of progress information.
        if opts.debug:
            d = lump.hdrdict
            print >> flog, (
                '   %-10s %-10s %s' %
                (d.get('Node-kind', ''), d['Node-action'], d['Node-path']))

        write_lump(fw, lump)

    fr.close()
    fw.close()


if __name__ == '__main__':
    main()

