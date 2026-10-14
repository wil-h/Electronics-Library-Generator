import os
import sys
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_THIS_DIR, 'lib')
for p in (_THIS_DIR, _LIB_DIR):
    if p not in sys.path:
        sys.path.append(p)

import asyncio
import re
import time
from pathlib import Path
import nodriver as uc
from nodriver import cdp

HUB_URL = "https://library.io/hubs/3187125-Components/libraries"

# Selectors not in your notes (login, loading, packages list) are guesses - adjust as needed.
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
PACKAGE_LINKS = "a[href*='/packages/']"      # GUESS: links in the packages list
PACKAGE_HREF_RE = re.compile(r"/packages/\d+")  # only real package pages, not nav links

DOWNLOAD_DIR = Path(os.path.join(os.path.dirname(__file__), 'CAD_FILES/packages'))
TIMEOUT = 60

USERNAME = ""#ENTER AUTODESK USERNAME HERE !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
PASSWORD = ""#ENTER AUTODESK PASSWORD HERE !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

class LibraryIO:
    def __init__(self):
        self.browser = None
        self.tab = None
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
        await asyncio.sleep(3)
        if USERNAME and PASSWORD:
            try:
                await (await self.tab.select(LOGIN_USER, timeout=30)).send_keys(USERNAME)
                await (await self.tab.select(LOGIN_NEXT)).click()
                await (await self.tab.select(LOGIN_PASS, timeout=30)).send_keys(PASSWORD)
                await (await self.tab.select(LOGIN_SUBMIT)).click()
            except: pass

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

    async def _current_url(self):
        return await self.tab.evaluate("window.location.href")

    async def _click_and_follow(self, element):
        """Click an element; if it opened a new browser tab, switch to it."""
        before = len(self.browser.tabs)
        await element.click()
        await self.tab.sleep(3)
        if len(self.browser.tabs) > before:
            self.tab = self.browser.tabs[-1]
            await self.tab.bring_to_front()
        await self._wait_loading_clear()

    def _add_urn_to_lib(self, part, urn):
            FILEPATH = os.path.join(_THIS_DIR, "CAD_FILES", "libs", f"{part}.lbr")
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

    # ---------------------------------------------------------------- flow steps
    async def _upload_lbr_to_hub(self, part):
        """Hub page -> "Upload File" -> part lbr, then wait for the upload to finish."""
        path = os.path.join(_THIS_DIR, "CAD_FILES", "libs", f"{part}.lbr")
        await self._goto(HUB_URL)
        await self._wait_loading_clear()
        upload_btn = await self.tab.find("Upload File", best_match=True, timeout=30)
        if not upload_btn:
            raise TimeoutError(f"Upload File button not found on {self.tab.url}")
        await self._upload_via_chooser(upload_btn, path)
        await self.tab.sleep(3)
        await self._wait_loading_clear()

    async def _open_newest_package(self):
        """"Packages" tab -> first (newest) package link. Returns the package page URL."""
        await (await self.tab.find("Packages", best_match=True, timeout=30)).click()
        await self.tab.sleep(2)
        await self._wait_loading_clear()
        await self.tab.select(PACKAGE_LINKS, timeout=30)
        links = await self.tab.select_all(PACKAGE_LINKS)
        first = next((l for l in links if PACKAGE_HREF_RE.search(l.attrs.get("href", ""))), None)
        if first is None:
            raise TimeoutError("No package links found in the Packages list")
        await first.click()
        await self.tab.sleep(2)
        await self._wait_loading_clear()
        return await self._current_url()

    async def _upload_model_in_editor(self, part):
        """Same package upload/save logic as before, but starting from the editor opened by "Edit"."""
        model_path = os.path.join(_THIS_DIR, "CAD_FILES", "3D", f"{part}.stp")

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

    async def _export_lbr(self, package_url):
        """Back on the saved package link -> "Export LBR". Returns the downloaded file path."""
        await self._goto(package_url)
        await self._wait_loading_clear()
        before = set(DOWNLOAD_DIR.glob("*.lbr"))
        await (await self.tab.find("Export LBR", best_match=True, timeout=60)).click()
        deadline = time.time() + 120
        while time.time() < deadline:
            new = [p for p in DOWNLOAD_DIR.glob("*.lbr") if p not in before]
            if new and not list(DOWNLOAD_DIR.glob("*.crdownload")):
                return max(new, key=lambda p: p.stat().st_mtime)
            await asyncio.sleep(1)
        raise TimeoutError("LBR download did not appear")

    async def _upload_new_version(self, part):
        path = os.path.join(_THIS_DIR, "CAD_FILES", "libs", f"{part}.lbr")
        await self._goto(HUB_URL)
        await self._wait_loading_clear()
        # the part link may open in a new tab, so follow it
        await self._click_and_follow(await self.tab.find(part, best_match=True, timeout=30))

        await (await self.tab.find("Upload New Version", best_match=True, timeout=30)).click()
        await self.tab.sleep(1)  # let the dialog open
        await self.tab.evaluate("document.getElementById('file').click()")  # "Upload from file" radio
        upload_file_btn = await self.tab.select(".newVersion button.button.gray", timeout=15)
        await self._upload_via_chooser(upload_file_btn, path)
        # the dialog's own "Upload" button (Cancel is the one with .transparent)
        await (await self.tab.select(".newVersion__row.buttons button:not(.transparent)", timeout=15)).click()

        # wait for the success message, clicking through the filename warning if it shows up
        js = """(() => {
            const vis = e => e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
            const ok = [...document.querySelectorAll('h2')].find(e => e.textContent.includes('New version successfully created'));
            if (ok && vis(ok)) return 'done';
            const cont = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Continue' && vis(b));
            if (cont) cont.click();
            return 'waiting';
        })()"""
        deadline = time.time() + 120
        while time.time() < deadline:
            if await self.tab.evaluate(js) == 'done':
                break
            await self.tab.sleep(0.5)
        else:
            raise TimeoutError("New version upload never reported success")

    # ---------------------------------------------------------------- full flow, one part at a time
    async def process_parts(self, files):
        for file in files:
            for f in os.listdir(DOWNLOAD_DIR):
                os.remove(os.path.join(DOWNLOAD_DIR, f))

            # 1. upload the lbr and wait for it to finish
            await self._upload_lbr_to_hub(file)

            # 2. Packages tab -> newest package, save its link
            package_url = await self._open_newest_package()

            # 3. "Edit" -> package upload/save logic in the editor
            hub_tab = self.tab
            await self._click_and_follow(await self.tab.find("Edit", best_match=True, timeout=30))
            editor_tab = self.tab
            await self._upload_model_in_editor(file)
            if editor_tab is not hub_tab:
                await editor_tab.close()
                self.tab = hub_tab

            # 4. back to the saved link -> "Export LBR"
            exported = await self._export_lbr(package_url)

            # 5. extract the URN and add it to the part lbr
            urn = self._extract_urn(exported)
            self._add_urn_to_lib(file, urn)
            os.remove(exported)

            # 6. part link -> "Upload New Version" -> updated lbr
            await self._upload_new_version(file)

            # 7. back to the main page for the next file
            await self._goto(HUB_URL)