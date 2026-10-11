import os
import sys
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_THIS_DIR, 'lib')
for p in (_THIS_DIR, _LIB_DIR):
    if p not in sys.path:
        sys.path.append(p)

import asyncio
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
import nodriver as uc
from nodriver import cdp

HUB_URL = "https://library.io/hubs/3187125-Components/libraries"
EDITOR_URL = "https://editor-package.library.io/?assetid=53916300#aHR0cHM6Ly9hcGkubGlicmFyeS5pbw"
PACKAGE_URL = "https://library.io/packages/53916300-HDRV1W64P0_1X1_200X200X838B"
 
# Selectors not in your notes (login, loading) are guesses - adjust as needed.
LOGIN_USER = "input[type='email'], input#userName, input[name='userName']"
LOGIN_NEXT = "button#verify_user_btn, button[type='submit']"
LOGIN_PASS = "input[type='password'], input#password"
LOGIN_SUBMIT = "button#btnSubmit, button[type='submit']"
UPLOAD_TAB = "a.js-editor__tab__subnav__button__btn[title='Upload STEP/F3D']"
UNSAVED = "span.js-version-btn.editor__topnav__version__btn--draft"
CREATE_VERSION = "a.js-toggle_draft"
VERSION_NAME = "input.js-name_input"
CREATE_BTN = "a.js-create_button"
LBR_INPUT = "input#import__file"
LOADING = ".loading, .spinner, .js-loading, .loader, [class*='loading']"
 
DOWNLOAD_DIR = Path(os.path.join(os.path.dirname(__file__), 'CAD_FILES/packages'))
TIMEOUT = 60

USERNAME = ""#ENTER AUTODESK USERNAME HERE !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
PASSWORD = ""#ENTER AUTODESK PASSWORD HERE !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

class LibraryIO:
    def __init__(self):
        self.browser = None
        self.tab = None
        if not USERNAME or not PASSWORD:
            raise RuntimeError("You need to manually enter your username and password in the LibraryIO.py file in the addin files")

    # ---------------------------------------------------------------- helpers
    async def _goto(self, url):
        self.tab = await self.browser.get(url)
        await self.tab.sleep(2)
 
    async def _wait_loading_clear(self):
        js = f"""(() => Array.from(document.querySelectorAll("{LOADING}")).some(e => {{
            const r = e.getBoundingClientRect(), s = getComputedStyle(e);
            return r.width > 0 && r.height > 0 && s.display !== 'none'
                   && s.visibility !== 'hidden' && s.opacity !== '0';
        }}))()"""
        deadline, clear = time.time() + TIMEOUT, 0
        while time.time() < deadline:
            clear = 0 if await self.tab.evaluate(js) else clear + 1
            if clear >= 3:
                return
            await self.tab.sleep(1)
        raise TimeoutError("Loading never cleared")
 
    async def _login(self):
        await self._goto(HUB_URL)
        await self._wait_loading_clear()
        await (await self.tab.select(LOGIN_USER, timeout=30)).send_keys(USERNAME)
        await (await self.tab.select(LOGIN_NEXT)).click()
        await (await self.tab.select(LOGIN_PASS, timeout=30)).send_keys(PASSWORD)
        await (await self.tab.select(LOGIN_SUBMIT)).click()
 
    async def start(self):
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.browser = await uc.start()
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            if self.browser:
                break
            await asyncio.sleep(2)
        else:
            raise TimeoutError("Browser Failed to start")
        await asyncio.sleep(2)
        await self._login()
        await self.tab.send(
            cdp.browser.set_download_behavior(
                behavior="allow", download_path=str(DOWNLOAD_DIR.resolve())
            )
        )
 
    async def stop(self):
        if self.browser:
            self.browser.stop()

    async def _upload_via_chooser(self, button, file_path):
        file_path = os.path.abspath(file_path)   # must be an absolute path
        done = asyncio.Event()

        async def on_chooser(event: cdp.page.FileChooserOpened):
            await self.tab.send(cdp.dom.set_file_input_files(
                files=[file_path],
                backend_node_id=event.backend_node_id,
            ))
            done.set()

        self.tab.add_handler(cdp.page.FileChooserOpened, on_chooser)
        await self.tab.send(cdp.page.enable())
        await self.tab.send(cdp.page.set_intercept_file_chooser_dialog(True))
        try:
            await button.click()
            await asyncio.wait_for(done.wait(), timeout=15)
        finally:
            await self.tab.send(cdp.page.set_intercept_file_chooser_dialog(False))
            self.tab.remove_handler(cdp.page.FileChooserOpened, on_chooser)

    def _add_urn_to_lib(self, part, urn):
            FILEPATH = os.path.join(_THIS_DIR, f"CAD_FILES\\libs\\{part}.lbr")
            with open(FILEPATH, 'r') as file:
                text = file.read()
            n, t = text.split("<package name=\"")
            packagename, n = t.split('"', 1)
            insert = f'''</packages>
        <packages3d>
        <package3d name="{part}" urn="{urn}" type="model">
            <packageinstances>
                <packageinstance name="{packagename}"/>
            </packageinstances>
        </package3d>
        </packages3d>'''
            text = text.replace("</packages>", insert)
            with open(FILEPATH, 'w') as file:
                file.write(text)

    def _extract_urn(self, filepath):
        with open(filepath, 'r') as file:
            text = file.read()
        n, text = text.split("<package3d name=\"", 1)
        n, text = text.split("\" urn=\"", 1)
        urn, n = text.split("\"", 1)
        return urn
    # ---------------------------------------------------------------- 1. model association
    async def associate_models(self, files):
        for file in files:
            await self._goto(EDITOR_URL)
            model_path = os.path.join(_THIS_DIR, f"CAD_FILES/3D/{file}.stp")
 
            # upload the 3D model in the editor
            await self._wait_loading_clear()
            upload_btn = await self.tab.select(UPLOAD_TAB, timeout=60)
            await self._upload_via_chooser(upload_btn, model_path)
            await self.tab.sleep(2)
            await self._wait_loading_clear()
 
            # create a version and wait for the save
            await self.tab.select(UNSAVED, timeout=TIMEOUT)
            await (await self.tab.select(CREATE_VERSION, timeout=30)).click()
            await self.tab.select(VERSION_NAME, timeout=15)
            await (await self.tab.select(CREATE_BTN, timeout=15)).click()
            deadline = time.time() + TIMEOUT
            while time.time() < deadline:
                await self.tab.sleep(1.5)
                if not await self.tab.evaluate(f"!!document.querySelector(\"{UNSAVED}\")"):
                    break
            else:
                raise TimeoutError("Version save did not finish")
            await self._wait_loading_clear()
 
            # export the LBR from the package page
            await self._goto(PACKAGE_URL)
            await self._wait_loading_clear()
            before = set(DOWNLOAD_DIR.glob("*.lbr"))
            await (await self.tab.find("Export LBR", best_match=True, timeout=60)).click()
            exported = None
            deadline = time.time() + 120
            while time.time() < deadline:
                new = [p for p in DOWNLOAD_DIR.glob("*.lbr") if p not in before]
                if new and not list(DOWNLOAD_DIR.glob("*.crdownload")):
                    exported = max(new, key=lambda p: p.stat().st_mtime)
                    break
                await asyncio.sleep(1)
            if exported is None:
                raise TimeoutError("LBR download did not appear")
            # extract the URN and add it to the new component
            f = os.listdir(os.path.join(_THIS_DIR,"CAD_FILES/packages"))[0]
            filepath = os.path.join(_THIS_DIR, f"CAD_FILES/packages/{f}")
            urn = self._extract_urn(filepath)
            self._add_urn_to_lib(file, urn)
            os.remove(filepath)            
    # ---------------------------------------------------------------- 2. upload modified files
    async def create_components(self, files):
        await self._goto(HUB_URL)
        for file in files:
            path = filepath = os.path.join(_THIS_DIR, f"CAD_FILES/libs/{file}.lbr")
            await self._wait_loading_clear()
            upload_btn = await self.tab.find("Upload File", best_match=True, timeout=30)
            if not upload_btn:
                raise TimeoutError(f"Upload File button not found on {self.tab.url}")
            await self._upload_via_chooser(upload_btn, path)
            await self.tab.sleep(3)
            await self._wait_loading_clear()

async def main():
    files = ["BC856B", "74LVC1G373DBVRE4"]
 
    bot = LibraryIO()
    await bot.start()
    await bot.associate_models(files)
    await bot.create_components(files)
 
 
if __name__ == "__main__":
    uc.loop().run_until_complete(main())