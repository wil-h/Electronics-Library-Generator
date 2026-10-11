from AWSServer import MouserClient
from componentSearchEnginev2 import ComponentSearchEngine
import os
import sys
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_THIS_DIR, 'lib')
for p in (_THIS_DIR, _LIB_DIR):
    if p not in sys.path:
        sys.path.append(p)

import requests
import asyncio
async def main():
    se = await ComponentSearchEngine.create()
    await se.login()
    print(await se.download_component("RT1206FRE07140KL"))
    print(await se.download_component("C0603F104K3RACTU"))
    print(await se.download_component("TLV1701AIDCKRG4"))
    await asyncio.sleep(5)


import shutil
import stat
def _remove_readonly(func,path,exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)

path = os.path.join(_THIS_DIR, "CAD_FILES")
if os.path.isdir(path):
    shutil.rmtree(path, onexc=_remove_readonly)
