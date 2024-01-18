import sys,os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setuptools
from __init__ import bl_info
with open("README.md", "r", encoding='utf-8') as fh:
    long_description = fh.read()

setuptools.setup(
    name="sssekai_blender_io",
    version='%s.%s.%s' % bl_info['version'],
    author="greats3an",
    author_email="greats3an@gmail.com",
    description="",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/mos9527/sssekai_blender_io",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    install_requires=["sssekai"],
    python_requires=">=3.8",
)
