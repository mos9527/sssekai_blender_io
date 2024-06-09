import os, re
path = os.path.dirname(__file__)
pattern = re.compile(r'^(?:msgid \")(?P<msgid>.*)(?:\".*)\n^(?:msgstr \")(?P<msgstr>.*)(?:\")$', re.MULTILINE)
translations_dict = dict()
for src in os.listdir(path):
    base, ext = os.path.splitext(src)
    if ext == '.po':
        lang = translations_dict[base] = dict()
        src = open(os.path.join(path, src), 'r', encoding='utf-8').read()
        lang.update({k:v for k,v in pattern.findall(src)})

from bpy.app.translations import locale
print('* Locale:', locale)
def get_text(id_str : str):
    return translations_dict.get(locale, {}).get(id_str, id_str) or id_str
