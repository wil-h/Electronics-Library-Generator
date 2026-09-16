import sys
import os
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_THIS_DIR, 'lib')
for p in (_THIS_DIR, _LIB_DIR):
    if p not in sys.path:
        sys.path.append(p)

import asyncio
import random
import json
import builtins
import nodriver as uc
from nodriver import cdp
import datetime

from AWSServer import EmailClient

DOWNLOAD_PATH = os.path.join(os.path.dirname(__file__), 'CAD_FILES')


class ComponentSearchEngine:
    def __init__(self):
        self.browser = None
        self.tab = None

    @classmethod
    async def create(cls):
        self = cls()
        self.browser = await self._launch_browser()
        self.tab = await self.browser.get("https://componentsearchengine.com/search")
        
        return self

    async def _setDownloads(self):
        # Route downloads to our folder - must be set per-tab via CDP.
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        await self.tab.send(
            cdp.page.set_download_behavior(behavior="allow", download_path=DOWNLOAD_PATH)
        )

    async def _launch_browser(self):
        browser = await uc.start()
        return browser

    async def login(self):
        if "login.json" not in os.listdir(os.path.dirname(__file__)):
            await self._register(self.tab)

        try:
            with builtins.open(os.path.join(os.path.dirname(__file__), "login.json"), 'r') as f:
                file = json.load(f)
            email = file.get("email", 0)
            password = file.get("password", 0)
            self.tab = await self.browser.get("https://componentsearchengine.com/signin")
            await asyncio.sleep(1)
            email_el = await self.tab.select("#email-address", timeout=30)
            await self._type(email_el, email)
            password_el = await self.tab.select("#password", timeout=30)
            await self._type(password_el, password)
            sign_in_btn = await self.tab.select("input.button.primary.is-large", timeout=30)
            await sign_in_btn.click()
            i=0
            while "learn-more" not in await self.tab.evaluate("window.location.href"):
                await asyncio.sleep(1)
                i+=1
                if i > 30:
                    raise RuntimeError()
            await asyncio.sleep(1)
        except:
            raise RuntimeError("problems accessing or entering login info")

    async def _type(self, element, text, delay=0.005):
        await element.apply("(elem) => elem.focus()")
        for char in text:
            await element.send_keys(char)
            await asyncio.sleep(delay)

    async def _register(self, tab):
        try:
            client = EmailClient()
            email = client.get_address()
            name, ext = email.split('@')
            first_name, last_name = name.split('.')
            password = self._gen_password()

            data = {
                "first_name": first_name,
                "last_name": last_name,
                "company": "WilHarAddin",
                "job_role_value": "14",
                "email": email,
                "password": password,
                "pw_confirm": password,
            }

            # navigating updates self.tab to the new page context
            tab = await self.browser.get("https://componentsearchengine.com/register")
            self.tab = tab

            # --- First Name ---
            first_name_el = await tab.select("#first-name", timeout=30)
            await self._type(first_name_el, data["first_name"])

            # --- Last Name ---
            last_name_el = await tab.select("#last-name")
            await self._type(last_name_el, data["last_name"])

            # --- Company ---
            company_el = await tab.select("#company")
            await self._type(company_el, data["company"])

            # --- Job Role (custom-styled <select>, transparent but present in DOM) ---
            # The visible text ("Choose Job Role") is just a styled overlay div;
            # the actual functional element is the <select id="job-role">.
            # nodriver's option.select_option() exists but is flagged upstream as
            # "does not work in all cases", so we set the value + fire a native
            # change event directly via JS, which every framework listener picks up.
            job_role_el = await tab.select("#job-role", timeout=30)
            await job_role_el.apply(
                f"""(el) => {{
                    el.value = '{data["job_role_value"]}';
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}"""
            )

            # --- Email ---
            email_el = await tab.select("#email-address")
            await self._type(email_el, data["email"])

            # --- Password ---
            password_el = await tab.select("#password")
            await self._type(password_el, data["password"])

            # --- Confirm Password ---
            pw_confirm_el = await tab.select("#pw-confirm")
            await self._type(pw_confirm_el, data["pw_confirm"])

            # --- Privacy checkbox ---
            # Same story as the job-role <select>: real <input> hidden behind a
            # custom-styled overlay, so a native/coordinate click can miss it.
            # We check state and click via JS, acting on the DOM node directly.
            privacy_checkbox = await tab.select("#confirm-privacy", timeout=30)
            is_checked = await privacy_checkbox.apply("(el) => el.checked")
            if not is_checked:
                await privacy_checkbox.apply("(el) => el.click()")
                is_checked = await privacy_checkbox.apply("(el) => el.checked")
                if not is_checked:
                    try:
                        label = await tab.select("label[for='confirm-privacy']")
                        await label.apply("(el) => el.click()")
                    except Exception:
                        pass

            # --- Submit ---
            await asyncio.sleep(5) #prevent bot detection by extending form completion time
            submit_btn = await tab.select("input.button.primary.is-large.track", timeout=30)
            await submit_btn.click()

            success_el = await tab.find("Account created successfully.", timeout=30)
            if success_el is None:
                raise RuntimeError()
        except:
            raise RuntimeError("Could not create new account")

        try:
            eclient = EmailClient()
            await asyncio.sleep(5)
            link = eclient.get_activation_link(email)
            if not link:
                await asyncio.sleep(10)
                link = eclient.get_activation_link(email)
                if not link:
                    raise RuntimeError()
            self.tab = await self.browser.get(link)
        except:
            raise RuntimeError("there was an error verifying the new account email")        
        #save the login info for future use
        with builtins.open(os.path.join(os.path.dirname(__file__), "login.json"), 'w') as file:
            file.write('{'+f"\"email\": \"{email}\", \"password\": \"{password}\", \"uses\": \"0\", \"date\": \"{datetime.date.today()}\""+'}')

    def _gen_password(self):
        letter_list = list("abcdefghijklmnopqrstuvwxyz")
        char_list = ['!', '$', '&', '%', '^', '#', '*']

        password = ""
        for _ in range(12):
            if random.randint(0, 1):
                next_char = random.choice(letter_list)
                if random.randint(0, 1):
                    next_char = next_char.upper()
            else:
                next_char = random.choice(char_list)
            password += next_char
        password += random.choice(letter_list)
        password += random.choice(letter_list).upper()
        password += random.choice(char_list)
        return password

    async def download_component(self, part_number):
        with open(os.path.join(os.path.dirname(__file__), "login.json"), 'r') as f:
            file = json.load(f)
        email = file.get("email",0)
        password = file.get("password",0)
        uses = file.get("uses",0)
        date = datetime.date.fromisoformat(file.get("date",0))
        if date != datetime.date.today(): uses = 0

        if int(uses) >= 15:
            self.tab = await self.browser.get("https://componentsearchengine.com/logout")
            await self._register(self.tab)
            await self.login()
            with open(os.path.join(os.path.dirname(__file__), "login.json"), 'r') as f:
                file = json.load(f)
                email = file.get("email",0)
                password = file.get("password",0)
                uses = file.get("uses",0)
                date = datetime.date.fromisoformat(file.get("date",0))

        try:
            if "/search" not in self.tab.url:
                self.tab = await self.browser.get("https://componentsearchengine.com/search")

            while not await self.tab.evaluate('''!!document.querySelector("input[name='term']")'''):
                await asyncio.sleep(0.3)
            await self.tab.evaluate("window.stop()")

            await self._setDownloads()
            search_el = await self.tab.select("input[name='term']", timeout=5)
            await self._type(search_el, part_number)

            search_btn = await self.tab.select("button.button.primary.is-bigger", timeout=30)
            await search_btn.click()

            while not await self.tab.evaluate('''!!document.querySelector("a[onclick*='Download Click']")''') and not await self.tab.evaluate('''!!document.querySelector("a.is-request-button")'''):
                await asyncio.sleep(0.3)
            await self.tab.evaluate("window.stop()")

            try:
                download_links = await self.tab.select_all("a[onclick*='Download Click']", timeout=3)
                download_btn = download_links[0]
                await download_btn.click()
            except:
                self.tab = await self.browser.get("https://componentsearchengine.com/search")
                await asyncio.sleep(1)
                await self.tab.evaluate("window.stop()")
                return False

            while not await self.tab.evaluate('''!!document.querySelector("a.ecad-model-button")'''):
                await asyncio.sleep(0.3)
            await self.tab.evaluate("window.stop()")

            ecad_download_btn = await self.tab.select("a.ecad-model-button", timeout=30)
            await ecad_download_btn.click()

            await asyncio.sleep(1)
            retry = False
            if await self.tab.evaluate('''document.body.innerText.includes("Error: Daily part download quota exceeded")'''):
                retry = True
                uses = 15
            with open(os.path.join(os.path.dirname(__file__), "login.json"), 'w') as f:
                f.write('{'+f"\"email\": \"{email}\", \"password\": \"{password}\", \"uses\": \"{int(uses)+1}\", \"date\": \"{datetime.date.today()}\""+'}')
            if retry:
                await self.tab.evaluate("window.stop()")
                await asyncio.sleep(0.5)
                await self.download_component(part_number)
        except Exception as e:
            return False
        return True

    async def close(self):
        self.browser.stop()