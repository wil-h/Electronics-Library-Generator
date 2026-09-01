def launch_browser():
    """
    Try Chrome first, fall back to Edge (pre-installed on most Windows
    machines even when Chrome isn't). Relies on Selenium Manager
    (built into selenium>=4.6) to auto-resolve the matching driver
    binary at runtime - no manual chromedriver/msedgedriver needed.
    """
    sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
 
    try:
        return webdriver.Chrome()
    except WebDriverException:
        pass
 
    try:
        return webdriver.Edge()
    except WebDriverException as e:
        raise RuntimeError(
            "Could not launch Chrome or Edge. Please make sure one of "
            "these browsers is installed, then try again."
        ) from e

def execute():
    driver = launch_browser()
    driver.get("https://www.mouser.com")
    time.sleep(5)
    driver.quit()