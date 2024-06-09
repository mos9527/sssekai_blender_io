import os, ast
os.chdir(os.path.join(os.path.dirname(__file__),'..'))

SOURCES = ['addon.py']

with open('i18n/en_US.po', 'w', encoding='utf-8') as po:
    po.write(r'''# mos9527 <greats3an@gmail.com>, 2024.
"Project-Id-Version: SSSekai Blender IO i18n\n"
"POT-Creation-Date: \n"
"PO-Revision-Date: \n"
"Last-Translator: \n"
"Language-Team: mos9527\n"
"Language: en_US\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
''')
    def parse_ast(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            src = ast.parse(f.read(), filename=filename)
            for node in ast.walk(src):
                if isinstance(node, ast.Call) and getattr(node.func,'id', None) == 'T':
                    po.writelines([
                        '#. :src: {filename}#L{node.lineno}',
                        'msgid "{node.args[0].value}"',
                        'msgstr ""\n'
                    ])
            pass
    for source in SOURCES:
        parse_ast(source)