# Assuming you have not changed the general structure of the template no modification is needed in this file.
from . import commands
import adsk.core
import adsk.fusion
import traceback
from selenium import webdriver
import time

# Global variables to keep handlers/objects alive
_app = None
_ui = None
_handlers = []

CMD_ID = 'helloWorldAddin_cmdBtn'
CMD_NAME = 'Generate Electronics Library'
CMD_DESCRIPTION = 'Creates an electronics library from an excel file with mouser numbers'
PANEL_ID = 'UtilitiesAddInsPanel'
WORKSPACE_ID = 'FusionSolidEnvironment'

def execute():
    driver = webdriver.Chrome()
    driver.get("www.google.com")
    time.sleep(5)
    driver.quit()

def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
 
        # Create the command definition
        cmd_defs = _ui.commandDefinitions
        cmd_def = cmd_defs.itemById(CMD_ID)
        if not cmd_def:
            cmd_def = cmd_defs.addButtonDefinition(
                CMD_ID,
                CMD_NAME,
                CMD_DESCRIPTION
                # You can add an icon folder path here as a 4th arg, e.g. './resources'
            )
 
        # Connect the command created event
        on_created = execute()
        cmd_def.commandCreated.add(on_created)
        _handlers.append(on_created)
 
        # Add a button to the toolbar panel
        workspace = _ui.workspaces.itemById(WORKSPACE_ID)
        panel = workspace.toolbarPanels.itemById(PANEL_ID)
        control = panel.controls.itemById(CMD_ID)
        if not control:
            control = panel.controls.addCommand(cmd_def)
            control.isPromoted = True
            control.isPromotedByDefault = True
 
    except:
        if _ui:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
 
 
def stop(context):
    try:
        workspace = _ui.workspaces.itemById(WORKSPACE_ID)
        panel = workspace.toolbarPanels.itemById(PANEL_ID)
        control = panel.controls.itemById(CMD_ID)
        if control:
            control.deleteMe()
 
        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
    except:
        if _ui:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))