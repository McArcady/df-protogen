from proto_renderer import ProtoRenderer
from cpp_renderer import CppRenderer


class GlobalTypeRenderer:

    def __init__(self, xml, ns, proto_ns='dfproto'):
        self.ns = ns
        self.proto_ns = proto_ns
        self.version = 2
        self.exceptions_rename = []
        self.exceptions_ignore = []
        self.exceptions_index = []
        self.exceptions_enum = []
        self.exceptions_depends = []
        self.ignore_no_export = True
        self.comment_ignored = False
        self.xml = xml
        assert self.xml.tag == '{%s}global-type' % (self.ns)

    def set_proto_version(self, ver):
        self.version = ver
        return self

    def set_exceptions_file(self, fname):
        with open(fname, 'r') as fil:
            for line in fil:
                tokens = line.strip().split(' ')
                if not tokens or tokens[0].startswith('#'):
                    continue
                if tokens[0] == 'rename':
                    self.exceptions_rename.append(tokens)
                elif tokens[0] == 'index':
                    self.exceptions_index.append(tokens)
                elif tokens[0] == 'ignore':
                    self.exceptions_ignore.append(tokens)
                elif tokens[0] == 'enum':
                    self.exceptions_enum.append(tokens)
                elif tokens[0] == 'depends':
                    self.exceptions_depends.append((tokens[1], tokens[2]))
    
    def set_ignore_no_export(self, b):
        self.ignore_no_export = b
        return self

    def set_comment_ignored(self, b):
        self.comment_ignored = b
        return self
    
    def get_type_name(self):
        tname = self.xml.get('type-name')
        if not tname:
            tname = self.xml.get('name')
        assert tname
        return tname           

    def get_meta_type(self):
        return self.xml.get('{%s}meta' % (self.ns))

    def get_instance_vector(self):
        return self.xml.get('instance-vector')        
    

    # main renderer

    def render_proto(self):
        rdr = ProtoRenderer(self.ns, self.proto_ns).set_version(self.version)
        rdr.set_comment_ignored(self.comment_ignored).set_ignore_no_export(self.ignore_no_export)
        for tokens in self.exceptions_rename:
            rdr.add_exception_rename(tokens[1], tokens[2])
        for tokens in self.exceptions_ignore:
            rdr.add_exception_ignore(tokens[1])
        for tokens in self.exceptions_index:
            rdr.add_exception_index(tokens[1], tokens[2])
        typout = rdr.render_type(self.xml)
        out  = '/* THIS FILE WAS GENERATED. DO NOT EDIT. */\n'
        out += 'syntax = "proto%d";\n' % (self.version)
        out += 'option optimize_for = LITE_RUNTIME;\n'
        for imp in rdr.imports:
            if imp != self.get_type_name():
                out += 'import \"%s.proto\";\n' % (imp)
        out += '\n' + typout
        return out

    def render_cpp(self):
        rdr = CppRenderer(self.ns, self.proto_ns, 'DFProto')
        rdr.set_comment_ignored(self.comment_ignored).set_ignore_no_export(self.ignore_no_export)
        for tokens in self.exceptions_rename:
            rdr.add_exception_rename(tokens[1], tokens[2])
        for tokens in self.exceptions_index:
            rdr.add_exception_index(tokens[1], tokens[2])
        for tokens in self.exceptions_ignore:
            rdr.add_exception_ignore(tokens[1])
        for tokens in self.exceptions_enum:
            rdr.add_exception_enum(tokens[1])
        typout = rdr.render_type(self.xml)
        out  = '/* THIS FILE WAS GENERATED. DO NOT EDIT. */\n'
        # this type may have hidden dependencies
        for k,v in self.exceptions_depends:
            if k == self.get_type_name():
                out += '#include \"%s.h\"\n' % (v)
        out += '#include \"%s.h\"\n' % (self.get_type_name())
        # protobuf and dfhack dependencies
        for imp in rdr.imports:
            out += '#include \"df/%s.h\"\n' % (imp)
            out += '#include \"%s.pb.h\"\n' % (imp)
        # conversion code for other types
        for imp in rdr.dfproto_imports:
            out += '#include \"%s.h\"\n' % (imp)
        out += '\n' + typout
        return out

    def render_h(self):
        rdr = CppRenderer(self.ns, self.proto_ns, 'DFProto')
        out  = '/* THIS FILE WAS GENERATED. DO NOT EDIT. */\n'
        out += '#include "DataDefs.h"\n'
        out += '#include "Export.h"\n'
        out += '#include <stdint.h>\n'
        out += '#include \"df/%s.h\"\n' % (self.get_type_name())
        out += '#include \"%s.pb.h\"\n' % (self.get_type_name())
        out += '\nnamespace DFProto {\n'
        out += '  %s\n' % (rdr.render_prototype(self.xml))
        out += '}\n'
        return out

    def render_to_files(self, proto_out, cpp_out, h_out):
        for k in self.exceptions_ignore:
            found = self.xml.getroottree().xpath(k[1], namespaces={
                'ld': self.ns,
                're': 'http://exslt.org/regular-expressions'
            })
            if found and self.xml in found:
                # ignore this type
                return None

        # generate code 
        proto_name = self.get_type_name() + '.proto'
        with open(proto_out + '/' + proto_name, 'w') as fil:
            fil.write(self.render_proto())
        if self.get_meta_type() in ['struct-type', 'class-type', 'enum-type', 'bitfield-type']:
            cpp_name = self.get_type_name() + '.cpp'
            with open(cpp_out + '/' + cpp_name, 'w') as fil:
                fil.write(self.render_cpp())
            h_name = self.get_type_name() + '.h'
            with open(h_out + '/' + h_name, 'w') as fil:
                fil.write(self.render_h())
            return (proto_name, cpp_name, h_name)
        return [proto_name]
