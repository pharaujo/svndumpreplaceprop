Introduction
============

`svndumpreplaceprop` is a command line tool used to alter properties (like
author, ou externals) directly on a svn dump. The main advantage over similar
tools is that it receives the svn dump through stdin and outputs the altered
dump to stdout. This makes it pipeable, so you can use it directly in a
svnadmin dump/load workflow.


Motivation
==========

I had a legacy svn repository I needed to move to a different server. The
repository was to move to a new domain too, so a need arose of correcting all
the hard-coded svn:externals properties. Also, while the old server was relying
on a htpasswd auth list with non-standard, legacy usernames, the new one was to
use LDAP-provided credentials, which were normalized to new company standards.

It became impractical using svnadmin to dump the 30GB repository to a file and
changing all properties that needed fixing.


Usage
=====

You can have `svndumpreplaceprop` transform the output of `svnadmin dump`
directly or using a dump file; same goes to loading your changes: either you
pipe it to a file, or directly to `svnadmin load`. The prop-map is a
csv-formatted file with the property you want to change, the string (regexp) to
search for, and a replacement. A sample prop-map file could be:

    "svn:author","foo","bar"
    "svn:author","baz","qux"
    "svn:externals","test.example.com:8080","example.com"


Example: Local direct usage
---------------------------

`svnadmin dump <repository_path> | ./svndumpreplaceprop.py --prop-map map.csv | svnadmin load <new_repository_path>`


Example: Remote direct usage
----------------------------

`svnadmin dump <repository_path> | ./svndumpreplaceprop.py --prop-map map.csv | ssh user@example.com svnadmin load <new_repository_path>`


Credits
=======

This code is mostly based on Martin Blais's excelent
[svndumpfilter3](http://furius.ca/pubcode/pub/conf/bin/svndumpfilter3). I
couldn't find a python module that abstracted the intricacies of svn dump nodes
(namely, reading and writing nodes, as well as rewriting lengths), so I kept the
Lump abstraction logic I needed and stripped the filter's functionality.
