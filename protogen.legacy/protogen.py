#!/usr/bin/env python3
#
# Generate and compile proto files with:
# $ ./protogen.py  ../df-structures && for f in $(ls protogen/*.proto); do echo $f &&  protoc -Iprotogen/ -otest.pb $f ||  break; done
#

import traceback
import sys
import argparse
import re
import os
import glob
from lxml import etree

from global_type_renderer import GlobalTypeRenderer

COLOR_OKBLUE = '\033[94m'
COLOR_FAIL = '\033[91m'
COLOR_ENDC = '\033[0m'

def snakeToCamelCase(string):
    string = string[0].upper() + string[1:]
    return re.sub(
        r'(?P<first>_[a-z])',
        lambda m: m.group('first')[1:].upper(),
        string
     )

def luaToCpp(string):
    string = string.replace('$global.', 'df::global::')
    string = string.replace('.', '->', 1)
    string = string.replace('world_data.', 'world_data->')
    return string

def main():
    
    # parse args
    parser = argparse.ArgumentParser(description='Generate protobuf and conversion code from dfhack structures.')
    parser.add_argument('input', metavar='DIR|FILE', type=str,
                        help='input directory or xml file (default=.)')
    parser.add_argument('--proto_out', metavar='PROTODIR', type=str,
                        default='./protogen',
                        help='output directory for protobuf files (default=./protogen)')
    parser.add_argument('--cpp_out', metavar='CPPDIR', type=str,
                        default='./protogen',
                        help='output directory for c++ files (default=./protogen)')
    parser.add_argument('--h_out', metavar='HDIR', type=str,
                        default='./protogen',
                        help='output directory for c++ headers (default=./protogen)')
    parser.add_argument('--methods', metavar='FILE', type=str,
                        default='./protogen/methods.inc',
                        help='generate macro file for global instance vectors (default=./protogen/methods.inc)')
    parser.add_argument('--grpc', metavar='FILE', type=str,
                        default='./protogen/grpc.proto',
                        help='generate protobuf procedures for querying instances (default=./protogen/grpc.proto)')
    parser.add_argument('--version', '-v', metavar='2|3', type=int,
                        default='2', help='protobuf version (default=2)')
    parser.add_argument('--quiet', '-q', action='store_true',
                        default=False, help='no output (default: False)')
    parser.add_argument('--debug', action='store_true',
                        default=False, help='show debug info (default: False)')
    parser.add_argument('--exceptions', metavar='EFILE', type=str,
                        default=None,
                        help='exceptions file (default=<none>)')
    parser.add_argument('--transform', metavar='XSLT', type=str, action='append',
                        default=[],
                        help='apply this transform before processing xml (default=<none>)')
    args = parser.parse_args()

    # input dir
    indir = args.input
    assert os.path.exists(indir)
    if os.path.isdir(indir) and not indir.endswith('/'):
        indir += '/'
    
    # output dir
    for outdir in [args.proto_out, args.cpp_out, args.h_out]:
        if not os.path.exists(outdir):
            os.mkdir(outdir)
            if not args.quiet:
                sys.stdout.write('created %s\n' % (outdir))

    # collect types
    transforms = [
        etree.XSLT(etree.parse(f)) for f in args.transform
    ]
    if transforms and not args.quiet:
        sys.stdout.write(COLOR_OKBLUE + 'using %s\n' % (', '.join(args.transform)) + COLOR_ENDC)
    instance_vectors = []
    filt = indir
    if os.path.isdir(indir):
        filt = indir+'df.*.xml'
    rc = 0
    for f in glob.glob(filt):
        if not args.quiet:
            sys.stdout.write(COLOR_OKBLUE + 'processing %s...\n' % (f) + COLOR_ENDC)

        # xml with all types of the structure
        struct_name = re.compile('df.(.*).xml').match(os.path.basename(f)).group(1)
        outxml = open(args.proto_out+'/df.%s.out.xml' % (struct_name), 'wb')
        assert struct_name, outxml
        
        xml = etree.parse(f)
        for t in transforms:
            xml = t(xml)
        ns = re.match(r'{(.*)}', xml.getroot().tag).group(1)
        xml.write(outxml)
        for item in xml.getroot():
            try:
                export = item.get('export')
                if export!='true' or 'global-type' not in item.tag:
                    if not args.quiet and args.debug:
                        sys.stdout.write('skipped type '+item.get('type-name') + '\n')
                    continue
                rdr = GlobalTypeRenderer(item, ns)
                rdr.set_proto_version(args.version)
                if args.debug:
                    rdr.set_comment_ignored(True)
                if args.exceptions:
                    rdr.set_exceptions_file(args.exceptions)
                fnames = rdr.render_to_files(args.proto_out, args.cpp_out, args.h_out)
                vector = rdr.get_instance_vector()
                if vector:
                    instance_vectors.append((rdr.get_type_name(), vector))
                if not args.quiet:
                    if fnames:
                        sys.stdout.write('created %s\n' % (', '.join(fnames)))
                    else:
                        sys.stdout.write('ignored type %s\n' % (rdr.get_type_name()))
            except Exception as e:
                _,_,tb = sys.exc_info()
                sys.stderr.write(COLOR_FAIL + 'error rendering type %s at line %d: %s\n' % (rdr.get_type_name(), item.sourceline if item.sourceline else 0, e) + COLOR_ENDC)
                traceback.print_tb(tb)
                rc = 1
                break

        outxml.close()
        if not args.quiet:
            sys.stdout.write('created %s\n' % (outxml.name))
        if rc:
            break

        # macros declaring RPC methods
        if args.methods:
            with open(args.methods, 'w') as fp:
                for v in instance_vectors:
                    fp.write("""
#ifndef DFPROTO_INCLUDED
#include "%s.h"
#endif
METHOD_GET_LIST(%s, %s, %s)
                    """ % ( v[0], snakeToCamelCase(v[0]),
                            v[0], luaToCpp(v[1])
                    ))
            if not args.quiet:
                sys.stdout.write('created %s\n' % (args.methods))

        # proto types for remote procedures
        if args.grpc:
            with open(args.grpc, 'w') as fp:
                for v in instance_vectors:
                    fp.write("""
import "%s.proto";
message %sList {
    repeated dfproto.%s list = 1;
}
                    """ % (v[0], snakeToCamelCase(v[0]), v[0])
                    )
            if not args.quiet:
                sys.stdout.write('created %s\n' % (args.grpc))
        
    sys.exit(rc)


if __name__ == "__main__":
    main()
